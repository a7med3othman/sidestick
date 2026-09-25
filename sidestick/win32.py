"""Small Windows helpers via ctypes. Every function is a safe no-op elsewhere."""

import logging
import os
import subprocess
import sys
import time

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes
    import winreg
    from ctypes import wintypes

    user32   = ctypes.WinDLL("user32",   use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32  = ctypes.WinDLL("shell32",  use_last_error=True)

    ULONG_PTR = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.GetWindowLongW.restype = ctypes.c_long
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    shell32.ShellExecuteW.restype = ctypes.c_void_p

INPUT_KEYBOARD    = 1
KEYEVENTF_KEYUP   = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CAPITAL        = 0x14
ERROR_ALREADY_EXISTS = 183

GWL_EXSTYLE       = -20
WS_EX_NOACTIVATE  = 0x08000000
SW_HIDE           = 0
SW_SHOWNOACTIVATE = 4
HWND_TOPMOST      = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010

# ── process setup ─────────────────────────────────────────────────────────

def set_dpi_aware():
    """Crisp (non-blurry) windows on high-DPI screens."""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # system DPI aware
    except Exception:
        try: user32.SetProcessDPIAware()
        except Exception: pass


def set_app_id(app_id):
    """Group our windows under our own taskbar icon instead of python.exe's."""
    if IS_WINDOWS:
        try: shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception: pass


def timer_resolution(ms, begin=True):
    """Raise the system timer resolution so short sleeps are accurate."""
    if IS_WINDOWS:
        try:
            winmm = ctypes.WinDLL("winmm")
            (winmm.timeBeginPeriod if begin else winmm.timeEndPeriod)(ms)
        except Exception:
            pass


def message_box(text, title):
    if IS_WINDOWS:
        user32.MessageBoxW(None, text, title, 0x40)   # MB_ICONINFORMATION
    else:
        print(f"{title}: {text}")


class SingleInstance:
    """Named mutex so two copies can't both drive the same controller."""

    def __init__(self, name):
        self.name   = name
        self.handle = None

    def acquire(self, wait=0.0):
        if not IS_WINDOWS:
            return True
        deadline = time.monotonic() + wait
        while True:
            h = kernel32.CreateMutexW(None, False, f"Local\\{self.name}")
            err = ctypes.get_last_error()
            if h and err != ERROR_ALREADY_EXISTS:
                self.handle = h
                return True
            if h:
                kernel32.CloseHandle(h)
            # NULL (access denied) means an elevated copy owns it
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.2)

    def release(self):
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None

# ── elevation ─────────────────────────────────────────────────────────────

def is_admin():
    if not IS_WINDOWS:
        return False
    try:    return bool(shell32.IsUserAnAdmin())
    except Exception: return False


def launch_command(extra_args=()):
    """(exe, args, cwd) that starts this app again, windowless."""
    if getattr(sys, "frozen", False):
        return sys.executable, list(extra_args), os.path.dirname(sys.executable)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    exe  = sys.executable
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pythonw):
        exe = pythonw
    return exe, [os.path.join(root, "Sidestick.pyw"), *extra_args], root


def relaunch_as_admin(extra_args=()):
    """Start an elevated copy (UAC prompt). Returns True if it was started."""
    if not IS_WINDOWS:
        return False
    exe, args, cwd = launch_command(extra_args)
    r = shell32.ShellExecuteW(None, "runas", exe, subprocess.list2cmdline(args), cwd, 1)
    return (r or 0) > 32

# ── start with Windows ────────────────────────────────────────────────────

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def get_startup(name):
    if not IS_WINDOWS:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, name)
            return True
    except OSError:
        return False


def set_startup(name, enabled, extra_args=("--minimized",)):
    if not IS_WINDOWS:
        return
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            exe, args, _ = launch_command(extra_args)
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ,
                              subprocess.list2cmdline([exe, *args]))
        else:
            try: winreg.DeleteValue(k, name)
            except FileNotFoundError: pass

# ── keyboard ──────────────────────────────────────────────────────────────

def caps_lock_on():
    if not IS_WINDOWS:
        return False
    return bool(user32.GetKeyState(VK_CAPITAL) & 1)


def send_unicode(text):
    """Type text exactly as given, ignoring Caps Lock / Shift / layout.
    Returns False if unsupported so the caller can fall back."""
    if not IS_WINDOWS:
        return False
    data  = text.encode("utf-16-le")
    units = [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]
    inputs = []
    for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
        for u in units:
            inp = INPUT(type=INPUT_KEYBOARD)
            inp.u.ki = KEYBDINPUT(0, u, flags, 0, 0)
            inputs.append(inp)
    arr = (INPUT * len(inputs))(*inputs)
    return user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT)) == len(inputs)

# ── windows ───────────────────────────────────────────────────────────────

def make_no_activate(hwnd):
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE)


_subclassed = {}   # hwnd → (new proc, old proc); keeps the callbacks alive

def block_mouse_activate(hwnd):
    """Stop mouse clicks from activating this window. WS_EX_NOACTIVATE alone
    isn't enough for Tk windows, so answer WM_MOUSEACTIVATE ourselves."""
    if not IS_WINDOWS or hwnd in _subclassed:
        return
    WM_MOUSEACTIVATE, MA_NOACTIVATE, GWLP_WNDPROC = 0x0021, 3, -4
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)
    user32.SetWindowLongPtrW.restype  = ctypes.c_void_p
    user32.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_void_p)
    user32.CallWindowProcW.restype    = LRESULT
    user32.CallWindowProcW.argtypes   = (ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                                         wintypes.WPARAM, wintypes.LPARAM)

    def proc(h, msg, wp, lp):
        if msg == WM_MOUSEACTIVATE:
            return MA_NOACTIVATE
        return user32.CallWindowProcW(old, h, msg, wp, lp)

    new = WNDPROC(proc)
    old = user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.cast(new, ctypes.c_void_p))
    _subclassed[hwnd] = (new, old)


def show_no_activate(hwnd):
    user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                        SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)


def hide_window(hwnd):
    user32.ShowWindow(hwnd, SW_HIDE)


def work_area():
    """(left, top, right, bottom) of the primary screen minus the taskbar."""
    if not IS_WINDOWS:
        return None
    r = wintypes.RECT()
    if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0):   # SPI_GETWORKAREA
        return r.left, r.top, r.right, r.bottom
    return None


def style_window(hwnd, caption_hex=None, rounded=True):
    """Dark title bar / caption colour / rounded corners (Windows 10+/11)."""
    if not IS_WINDOWS or not hwnd:
        return
    try:
        dwm = ctypes.WinDLL("dwmapi")
        def attr(n, value):
            v = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), n, ctypes.byref(v), ctypes.sizeof(v))
        attr(20, 1)                                  # DWMWA_USE_IMMERSIVE_DARK_MODE
        if caption_hex:
            r, g, b = (int(caption_hex[i:i + 2], 16) for i in (1, 3, 5))
            attr(35, r | (g << 8) | (b << 16))       # DWMWA_CAPTION_COLOR
        if rounded:
            attr(33, 2)                              # DWMWA_WINDOW_CORNER_PREFERENCE = ROUND
    except Exception:
        pass
