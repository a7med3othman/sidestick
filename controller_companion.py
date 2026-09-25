#!/usr/bin/env python3
"""
Controller Companion — Xbox Series X gamepad → mouse + keyboard
Requirements: pip install pygame pynput
Usage:        python controller_companion.py
"""

import os
import signal
import sys
import time
import tkinter as tk

# Keep reading the controller while other apps have focus, and skip pygame's banner.
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
import pygame.locals as PGL

from pynput.mouse    import Button as MButton, Controller as MouseCtrl
from pynput.keyboard import Key, KeyCode, Controller as KbCtrl

# ═══════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

MOUSE_SPEED        = 18
SCROLL_SPEED       = 5
DEADZONE           = 0.15
TRIGGER_THRESHOLD  = 0.25
REPEAT_DELAY       = 0.35
REPEAT_RATE        = 0.06
TICK_MS            = 16
ACCEL_POWER        = 2.0   # 1.0 = linear, 2.0 = smooth acceleration curve
BACK_TAP_MAX       = 0.5   # Back released within this many seconds (and unused
                           # as a modifier) counts as a tap → Escape
RECONNECT_INTERVAL = 1.5   # seconds between controller re-scans while disconnected

# ── Virtual keyboard appearance ────────────────────────────────────────────
VK_KEY_WIDTH       = 3     # key cell width  (characters)
VK_KEY_HEIGHT      = 1     # key cell height (lines)
VK_KEY_FONT_SIZE   = 11    # key label font size
VK_KEY_PADX        = 2     # horizontal padding inside each key
VK_KEY_PADY        = 3     # vertical padding inside each key
VK_KEY_GAP         = 2     # gap between keys (pixels)

# ── Confirmed axis map for Xbox Series X on Windows/SDL ───────────────────
#   ax0 = Left Stick X   (left=-1, right=+1)
#   ax1 = Left Stick Y   (up=-1,   down=+1)
#   ax2 = Right Stick X  (left=-1, right=+1)
#   ax3 = Right Stick Y  (up=-1,   down=+1)
#   ax4 = Left Trigger   (rest=-1, full=+1)
#   ax5 = Right Trigger  (rest=-1, full=+1)

AXIS_LX = 0
AXIS_LY = 1
AXIS_RX = 2
AXIS_RY = 3
AXIS_LT = 4
AXIS_RT = 5

# ── Xbox button indices ────────────────────────────────────────────────────
BTN_A, BTN_B, BTN_X, BTN_Y = 0, 1, 2, 3
BTN_LB, BTN_RB              = 4, 5
BTN_BACK, BTN_START         = 6, 7
BTN_LS, BTN_RS              = 8, 9
HAT_IDX                     = 0

# ═══════════════════════════════════════════════════════════════════════════
#  COLOURS
# ═══════════════════════════════════════════════════════════════════════════

BG      = "#111008"
CARD_BG = "#1e1b0f"
ACCENT  = "#f97316"
TEXT    = "#fef3c7"
DIM     = "#57534e"
HEADER  = "#fbbf24"

# ═══════════════════════════════════════════════════════════════════════════
#  VIRTUAL KEYBOARD
# ═══════════════════════════════════════════════════════════════════════════

# Each key is (normal, shifted)
VK_ROWS = [
    [('`','~'),('1','!'),('2','@'),('3','#'),('4','$'),('5','%'),
     ('6','^'),('7','&'),('8','*'),('9','('),('0',')'),('-','_'),('=','+')],
    [('q','Q'),('w','W'),('e','E'),('r','R'),('t','T'),('y','Y'),
     ('u','U'),('i','I'),('o','O'),('p','P'),('[','{'),  (']','}'),  ('\\','|')],
    [('a','A'),('s','S'),('d','D'),('f','F'),('g','G'),('h','H'),
     ('j','J'),('k','K'),('l','L'),(';',':'),("'",'"')],
    [('z','Z'),('x','X'),('c','C'),('v','V'),('b','B'),('n','N'),
     ('m','M'),(',','<'),('.','>'),(  '/','?')],
]
VK_ROWS_N = len(VK_ROWS)

def vk_char(row, col, shifted):
    pair = VK_ROWS[row][col]
    return pair[1] if shifted else pair[0]

def vk_display(row, col, shifted):
    return vk_char(row, col, shifted).upper() if not shifted else vk_char(row, col, shifted)

# ═══════════════════════════════════════════════════════════════════════════
#  NON-ACTIVATING WINDOWS (overlay + virtual keyboard)
# ═══════════════════════════════════════════════════════════════════════════
#
# Tk's deiconify() activates the window, which steals keyboard focus from the
# app you're typing into. Instead, the native window is created once, marked
# WS_EX_NOACTIVATE, and shown/hidden directly with ShowWindow(SW_SHOWNOACTIVATE)
# so the foreground window never changes — not even when the window is clicked.

GWL_EXSTYLE       = -20
WS_EX_NOACTIVATE  = 0x08000000
SW_HIDE           = 0
SW_SHOWNOACTIVATE = 4
HWND_TOPMOST      = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010

class NoActivateWindow:
    def __init__(self, root, title):
        self.win = tk.Toplevel(root)
        self.win.title(title)
        self.win.configure(bg=BG)
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self.hide)
        self._visible = False
        self._hwnd    = None
        try:
            self.win.attributes("-toolwindow", True)   # no taskbar / Alt+Tab entry
        except tk.TclError:
            pass
        self.win.attributes("-topmost", True)

    def realize(self):
        """Call once after the window's contents are built."""
        if sys.platform == "win32":
            try:
                import ctypes
                self._u32 = ctypes.windll.user32
                # Map once off-screen so Tk creates the native wrapper window.
                self.win.geometry("+-32000+-32000")
                self.win.update_idletasks()
                self.win.update()
                hwnd = int(self.win.wm_frame(), 16)
                self._u32.ShowWindow(hwnd, SW_HIDE)
                style = self._u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                self._u32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE)
                self._hwnd = hwnd
                return
            except Exception as e:
                print(f"[Window] No-activate setup failed, falling back: {e}")
        self.win.withdraw()

    def place_bottom_center(self, margin=60):
        self.win.update_idletasks()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        w,  h  = self.win.winfo_reqwidth(),   self.win.winfo_reqheight()
        self.win.geometry(f"+{(sw - w) // 2}+{max(0, sh - h - margin)}")

    def place_center(self):
        self.win.update_idletasks()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        w,  h  = self.win.winfo_reqwidth(),   self.win.winfo_reqheight()
        self.win.geometry(f"+{(sw - w) // 2}+{max(0, (sh - h) // 2)}")

    def show(self):
        if self._hwnd:
            self._u32.ShowWindow(self._hwnd, SW_SHOWNOACTIVATE)
            self._u32.SetWindowPos(self._hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                   SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
        else:
            self.win.deiconify(); self.win.lift()
        self._visible = True

    def hide(self):
        if self._hwnd:
            self._u32.ShowWindow(self._hwnd, SW_HIDE)
        else:
            self.win.withdraw()
        self._visible = False

    def toggle(self):
        self.hide() if self._visible else self.show()

    def is_visible(self): return self._visible

# ═══════════════════════════════════════════════════════════════════════════
#  SETTINGS WINDOW
# ═══════════════════════════════════════════════════════════════════════════

class SettingsWindow:
    def __init__(self, root, get_vals, set_vals):
        self._get = get_vals
        self._set = set_vals
        self.win = tk.Toplevel(root)
        self.win.title("Settings — Controller Companion")
        self.win.configure(bg=BG)
        self.win.attributes("-topmost", True)
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self.hide)
        self.win.withdraw()
        self._build()

    def _build(self):
        tk.Label(self.win, text="⚙  SENSITIVITY SETTINGS",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=16, pady=(12,2))
        tk.Frame(self.win, bg=ACCENT, height=1).pack(fill="x", padx=16, pady=(0,10))
        card = tk.Frame(self.win, bg=CARD_BG, padx=18, pady=14)
        card.pack(padx=16, pady=(0,6), fill="x")
        ms, ss, dz, ap = self._get()
        self._label_refreshers = []
        self._mouse_var  = tk.DoubleVar(value=ms)
        self._scroll_var = tk.DoubleVar(value=ss)
        self._dz_var     = tk.DoubleVar(value=dz)
        self._accel_var  = tk.DoubleVar(value=ap)
        self._add_slider(card, 0, "Mouse Speed",     "How fast the cursor moves",
                         self._mouse_var,  1, 60,  1,    lambda v: f"{int(v)}",  "px/frame")
        self._add_slider(card, 1, "Scroll Speed",    "Lines scrolled per frame",
                         self._scroll_var, 1, 20,  1,    lambda v: f"{int(v)}",  "lines")
        self._add_slider(card, 2, "Stick Dead-Zone", "Ignore stick movement below this",
                         self._dz_var,  0.0, 0.5, 0.01,  lambda v: f"{v:.2f}",  "")
        self._add_slider(card, 3, "Mouse Acceleration",
                         "1.0 = linear  |  2.0 = smooth curve  |  3.0 = heavy curve",
                         self._accel_var, 1.0, 4.0, 0.1,
                         lambda v: ("Linear" if abs(float(v)-1.0)<0.05
                                    else f"Power {float(v):.1f}"), "")
        btn_row = tk.Frame(self.win, bg=BG)
        btn_row.pack(pady=(4,14), padx=16, fill="x")
        tk.Button(btn_row, text="Apply", bg=ACCENT, fg=BG,
                  font=("Segoe UI",9,"bold"), relief="flat", padx=14, pady=4,
                  cursor="hand2", command=self._apply).pack(side="left")
        tk.Button(btn_row, text="Reset Defaults", bg=CARD_BG, fg=DIM,
                  font=("Segoe UI",9), relief="flat", padx=14, pady=4,
                  cursor="hand2", command=self._reset).pack(side="left", padx=(8,0))
        self._status = tk.Label(btn_row, text="", bg=BG, fg=HEADER,
                                font=("Segoe UI",8))
        self._status.pack(side="right")

    def _add_slider(self, parent, row, label, desc, var, from_, to, res, fmt, unit):
        tk.Label(parent, text=label, bg=CARD_BG, fg=TEXT,
                 font=("Segoe UI",9,"bold"), anchor="w", width=18).grid(
                     row=row*2, column=0, sticky="w", pady=(8 if row else 0, 0))
        tk.Label(parent, text=desc, bg=CARD_BG, fg=DIM,
                 font=("Segoe UI",7), anchor="w").grid(row=row*2+1, column=0, sticky="w")
        val_lbl = tk.Label(parent,
                           text=fmt(var.get())+(" "+unit if unit else ""),
                           bg=CARD_BG, fg=ACCENT,
                           font=("Segoe UI",9,"bold"), width=10, anchor="e")
        val_lbl.grid(row=row*2, column=2, rowspan=2, sticky="e", padx=(8,0))
        def refresh(lbl=val_lbl, f=fmt, u=unit):
            lbl.config(text=f(var.get())+(" "+u if u else ""))
        # Scale's command only fires on user drags, not on var.set(), so
        # show()/reset refresh the value labels explicitly.
        self._label_refreshers.append(refresh)
        def on_change(v):
            refresh()
            self._apply_live()
        tk.Scale(parent, variable=var, from_=from_, to=to, resolution=res,
                 orient="horizontal", length=260, bg=CARD_BG, fg=ACCENT,
                 troughcolor=BG, highlightthickness=0, sliderrelief="flat",
                 showvalue=False, command=on_change).grid(
                     row=row*2, column=1, rowspan=2, padx=(12,8), sticky="ew")

    def _apply_live(self):
        self._set(self._mouse_var.get(), self._scroll_var.get(),
                  self._dz_var.get(), self._accel_var.get())

    def _apply(self):
        self._apply_live()
        self._status.config(text="✓ Saved")
        self.win.after(1500, lambda: self._status.config(text=""))

    def _refresh_labels(self):
        for refresh in self._label_refreshers:
            refresh()

    def _reset(self):
        self._mouse_var.set(MOUSE_SPEED); self._scroll_var.set(SCROLL_SPEED)
        self._dz_var.set(DEADZONE);       self._accel_var.set(ACCEL_POWER)
        self._refresh_labels()
        self._apply_live()
        self._status.config(text="✓ Reset to defaults")
        self.win.after(1500, lambda: self._status.config(text=""))

    def show(self):
        ms, ss, dz, ap = self._get()
        self._mouse_var.set(ms); self._scroll_var.set(ss)
        self._dz_var.set(dz);    self._accel_var.set(ap)
        self._refresh_labels()
        self.win.deiconify(); self.win.lift()

    def hide(self): self.win.withdraw()
    def toggle(self):
        if self.win.state() == "withdrawn": self.show()
        else: self.hide()

# ═══════════════════════════════════════════════════════════════════════════
#  OVERLAY
# ═══════════════════════════════════════════════════════════════════════════

OVERLAY_BINDINGS = {
    "PRIMARY": [
        ("Left Stick",  "Move mouse"),
        ("Right Stick", "Scroll"),
        ("A",           "Left click"),
        ("X",           "Right click"),
        ("Y",           "Play/Pause"),
        ("LB / RB",     "Prev/Next track"),
        ("LT (hold)",   "Left Shift"),
        ("RT (hold)",   "Left Ctrl"),
        ("D-Pad",       "Arrow keys"),
        ("Start",       "Enter"),
        ("Back (tap)",  "Escape"),
        ("LS click",    "Virtual keyboard"),
        ("RS click",    "This overlay"),
    ],
    "HOLD BACK": [
        ("D-Pad ↑",  "Volume up"),
        ("D-Pad ↓",  "Volume down"),
        ("D-Pad ←",  "Mute"),
        ("X",        "Refresh (F5)"),
        ("Y",        "Close (Alt+F4)"),
        ("A",        "Double click"),
        ("LB",       "Alt+Tab"),
    ],
    "VIRTUAL KB": [
        ("Stick/D-Pad","Navigate"),
        ("A",          "Type key"),
        ("Y",          "Space"),
        ("X",          "Backspace"),
        ("B",          "Delete"),
        ("Start",      "Enter"),
        ("RS click",   "Tab"),
        ("LT",         "Shift"),
        ("RT",         "AltGr"),
        ("Back",       "Caps Lock"),
        ("LB / RB",    "Smaller / Bigger"),
        ("LS click",   "Close"),
    ],
}

def build_overlay(root):
    overlay = NoActivateWindow(root, "Controller Companion – Bindings")
    win = overlay.win
    win.attributes("-alpha", 0.93)
    tk.Label(win, text="🎮  CONTROLLER COMPANION",
             bg=BG, fg=ACCENT,
             font=("Segoe UI",12,"bold")).pack(anchor="w", padx=14, pady=(10,2))
    tk.Frame(win, bg=ACCENT, height=1).pack(fill="x", padx=14, pady=(0,8))
    cols = tk.Frame(win, bg=BG)
    cols.pack(padx=10, pady=(0,12))
    for section, pairs in OVERLAY_BINDINGS.items():
        col = tk.Frame(cols, bg=CARD_BG, padx=8, pady=6)
        col.pack(side="left", fill="y", padx=5)
        tk.Label(col, text=section, bg=CARD_BG, fg=HEADER,
                 font=("Segoe UI",8,"bold")).grid(
                     row=0, column=0, columnspan=2, sticky="w", pady=(0,4))
        for i, (btn, desc) in enumerate(pairs, 1):
            tk.Label(col, text=btn, bg=CARD_BG, fg=ACCENT,
                     font=("Segoe UI",8,"bold"),
                     width=12, anchor="w").grid(row=i, column=0, sticky="w", pady=1)
            tk.Label(col, text=desc, bg=CARD_BG, fg=TEXT,
                     font=("Segoe UI",8),
                     anchor="w").grid(row=i, column=1, sticky="w", padx=(3,0), pady=1)
    overlay.realize()
    overlay.place_center()
    return overlay

# ═══════════════════════════════════════════════════════════════════════════
#  VIRTUAL KEYBOARD WINDOW
# ═══════════════════════════════════════════════════════════════════════════

class VirtualKeyboard(NoActivateWindow):
    def __init__(self, root):
        super().__init__(root, "Virtual Keyboard")
        self.root = root
        self.row       = 0
        self.col       = 0
        self.shift_on  = False
        self.altgr_on  = False
        self._scale    = 1.0   # 0.5 = small .. 2.5 = large
        self._build()
        self.realize()

    def _build(self):
        hdr = tk.Frame(self.win, bg=BG)
        hdr.pack(fill="x", padx=10, pady=(8,2))
        tk.Label(hdr, text="⌨️  VIRTUAL KEYBOARD",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI",10,"bold")).pack(side="left")
        self.mod_lbl = tk.Label(hdr, text="", bg=BG, fg=HEADER,
                                font=("Segoe UI",9,"bold"))
        self.mod_lbl.pack(side="right")
        tk.Frame(self.win, bg=ACCENT, height=1).pack(fill="x", padx=10)
        gf = tk.Frame(self.win, bg=BG)
        gf.pack(padx=10, pady=8)
        self.cells = []
        for r, row in enumerate(VK_ROWS):
            row_cells = []
            for c, pair in enumerate(row):
                lbl = tk.Label(gf, text=vk_display(r, c, False),
                               width=VK_KEY_WIDTH, height=VK_KEY_HEIGHT,
                               bg=CARD_BG, fg=TEXT, relief="flat",
                               font=("Segoe UI", VK_KEY_FONT_SIZE, "bold"),
                               padx=VK_KEY_PADX, pady=VK_KEY_PADY)
                lbl.grid(row=r, column=c, padx=VK_KEY_GAP, pady=VK_KEY_GAP)
                row_cells.append(lbl)
            self.cells.append(row_cells)
        # ── hint bar row 1: typing actions ───────────────────────────────
        hint1 = tk.Frame(self.win, bg=BG)
        hint1.pack(pady=(0,2))
        for text, fg in [("A=Type",ACCENT),("Y=Space",TEXT),("X=Bksp",TEXT),
                         ("B=Del",TEXT),("Start=↵",TEXT),("RS↓=Tab",TEXT),
                         ("LT=Shift",HEADER),("RT=AltGr",HEADER)]:
            tk.Label(hint1, text=text, bg=CARD_BG, fg=fg,
                     font=("Segoe UI",8), padx=5, pady=2).pack(side="left", padx=2)
        # ── hint bar row 2: nav / size ────────────────────────────────────
        hint2 = tk.Frame(self.win, bg=BG)
        hint2.pack(pady=(0,6))
        for text, fg in [("Stick/D-Pad=Move",DIM),("LS↓=Close",DIM),
                         ("LB=Smaller",DIM),("RB=Bigger",DIM)]:
            tk.Label(hint2, text=text, bg=CARD_BG, fg=fg,
                     font=("Segoe UI",8), padx=5, pady=2).pack(side="left", padx=2)
        self._size_lbl = tk.Label(hint2, text="100%", bg=CARD_BG, fg=ACCENT,
                                  font=("Segoe UI",8,"bold"), padx=5, pady=2)
        self._size_lbl.pack(side="left", padx=2)
        self._highlight()

    def _highlight(self):
        for r, row in enumerate(self.cells):
            for c, cell in enumerate(row):
                sel = (r == self.row and c == self.col)
                cell.config(bg=ACCENT if sel else CARD_BG,
                            fg=BG     if sel else TEXT)

    def move(self, dx, dy):
        nr = max(0, min(VK_ROWS_N-1, self.row + dy))
        nc = max(0, min(len(VK_ROWS[nr])-1, self.col + dx))
        if nr != self.row or nc != self.col:
            self.row, self.col = nr, nc
            self._highlight()

    def type_selected(self, kb):
        char = vk_char(self.row, self.col, self.shift_on)
        if self.altgr_on: kb.press(Key.alt_gr)
        try:
            kb.press(KeyCode.from_char(char))
            kb.release(KeyCode.from_char(char))
        finally:
            if self.altgr_on: kb.release(Key.alt_gr)

    def set_shift(self, on):
        if on == self.shift_on:
            return
        self.shift_on = on
        self._refresh_mod()
        for r, row in enumerate(self.cells):
            for c, cell in enumerate(row):
                cell.config(text=vk_display(r, c, on))
        self._highlight()

    def set_altgr(self, on):
        if on == self.altgr_on:
            return
        self.altgr_on = on
        self._refresh_mod()

    def _refresh_mod(self):
        parts = (["SHIFT"] if self.shift_on else []) + (["ALTGR"] if self.altgr_on else [])
        self.mod_lbl.config(text="  ".join(parts))

    def resize(self, delta):
        """delta: +0.1 = bigger, -0.1 = smaller. Clamped 50%–250%."""
        self._scale = max(0.5, min(2.5, self._scale + delta))
        fs   = max(7,  int(VK_KEY_FONT_SIZE   * self._scale))
        padx = max(1,  int(VK_KEY_PADX        * self._scale))
        pady = max(1,  int(VK_KEY_PADY        * self._scale))
        w    = max(2,  int(VK_KEY_WIDTH       * self._scale))
        gap  = max(1,  int(VK_KEY_GAP         * self._scale))
        for row in self.cells:
            for cell in row:
                cell.config(font=("Segoe UI", fs, "bold"),
                            width=w, padx=padx, pady=pady)
                cell.grid_configure(padx=gap, pady=gap)
        self._size_lbl.config(text=f"{int(round(self._scale*100))}%")
        self.place_bottom_center()

    def show(self):
        # Position while still hidden, then show without taking focus.
        self.place_bottom_center()
        super().show()

# ═══════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════

class ControllerCompanion:

    def __init__(self):
        pygame.init()
        pygame.joystick.init()
        self.mouse   = MouseCtrl()
        self.kb      = KbCtrl()
        self.running = True
        self.js      = None
        self._next_connect_try = 0.0

        # live sensitivity
        self.mouse_speed  = float(MOUSE_SPEED)
        self.scroll_speed = float(SCROLL_SPEED)
        self.deadzone     = float(DEADZONE)
        self.accel_power  = float(ACCEL_POWER)

        # button/hat state
        self.prev_btn  = [False] * 16
        self.prev_hat  = (0, 0)
        self._alt_tab_active = False
        self._back_down_at   = float("-inf")
        self._back_chorded   = False   # Back was used as a modifier this hold

        # Everything we press is tracked here so it can always be released
        # (disconnect, crash, quit) and nothing is left stuck down.
        self._held_keys  = set()
        self._held_mouse = set()

        # Triggers can report 0.0 (= "half pressed") until first moved, so each
        # trigger stays ignored until it has been seen at rest or has moved.
        self._trig_armed   = {AXIS_LT: False, AXIS_RT: False}
        self._trig_initial = {AXIS_LT: 0.0,   AXIS_RT: 0.0}

        # sub-step accumulators for mouse + scroll
        self._move_accum   = [0.0, 0.0]
        self._scroll_accum = 0.0

        # VK stick/dpad repeat
        self.vk_last_dir   = (0, 0)
        self.vk_move_until = 0.0

        # ── Tk root ────────────────────────────────────────────────────────
        self.root = tk.Tk()
        self.root.title("Controller Companion")
        self.root.geometry("320x100")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        tk.Label(self.root, text="🎮  Controller Companion  —  Running",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI",10,"bold")).pack(pady=(10,2))
        tk.Label(self.root,
                 text="RS click = overlay    LS click = keyboard    close to quit",
                 bg=BG, fg=DIM,
                 font=("Segoe UI",7)).pack()
        tk.Button(self.root, text="⚙  Sensitivity Settings",
                  bg=CARD_BG, fg=ACCENT,
                  font=("Segoe UI",8,"bold"),
                  relief="flat", padx=10, pady=3,
                  cursor="hand2",
                  command=lambda: self.settings.toggle()).pack(pady=(6,0))

        self.overlay  = build_overlay(self.root)
        self.vk       = VirtualKeyboard(self.root)
        self.settings = SettingsWindow(
            self.root,
            get_vals=lambda: (self.mouse_speed, self.scroll_speed, self.deadzone, self.accel_power),
            set_vals=self._apply_settings,
        )

    # ── axis reading ───────────────────────────────────────────────────────

    def _raw(self, ax):
        try:    return self.js.get_axis(ax)
        except Exception: return 0.0

    def _stick(self, ax):
        """
        Read a stick axis. Applies deadzone, returns -1.0 to +1.0.
        Sticks on this controller rest at 0.0 so no offset needed.
        Up/left = negative, down/right = positive.
        """
        v  = self._raw(ax)
        dz = self.deadzone
        if abs(v) < dz:
            return 0.0
        s = 1.0 if v > 0 else -1.0
        return s * (abs(v) - dz) / (1.0 - dz)

    def _trigger(self, ax):
        """
        Read a trigger axis.
        This controller's triggers rest at -1.0 and go to +1.0 when pressed.
        Returns 0.0 (released) to 1.0 (fully pressed).
        """
        raw = self._raw(ax)
        if not self._trig_armed[ax]:
            if raw < -0.5 or abs(raw - self._trig_initial[ax]) > 0.05:
                self._trig_armed[ax] = True
            else:
                return 0.0
        # remap -1..+1 → 0..1
        return (raw + 1.0) / 2.0

    def _hat(self):
        try:    return self.js.get_hat(HAT_IDX)
        except Exception: return (0, 0)

    def _hat_presses(self, hat):
        """D-pad directions that became pressed this tick (diagonals give two)."""
        (hx, hy), (px, py) = hat, self.prev_hat
        dirs = []
        if hy ==  1 and py !=  1: dirs.append("up")
        if hy == -1 and py != -1: dirs.append("down")
        if hx == -1 and px != -1: dirs.append("left")
        if hx ==  1 and px !=  1: dirs.append("right")
        return dirs

    def _btn(self, i):
        try:    return bool(self.js.get_button(i))
        except Exception: return False

    def _pressed(self, i):  return self._btn(i) and not self.prev_btn[i]
    def _released(self, i): return not self._btn(i) and self.prev_btn[i]

    # ── output (tracked) ───────────────────────────────────────────────────

    def _tap(self, key):
        try:     self.kb.press(key)
        finally: self.kb.release(key)

    def _set_key(self, key, down):
        if down and key not in self._held_keys:
            self.kb.press(key);   self._held_keys.add(key)
        elif not down and key in self._held_keys:
            self._held_keys.discard(key); self.kb.release(key)

    def _set_mouse(self, button, down):
        if down and button not in self._held_mouse:
            self.mouse.press(button);   self._held_mouse.add(button)
        elif not down and button in self._held_mouse:
            self._held_mouse.discard(button); self.mouse.release(button)

    def release_all(self):
        """Let go of every key and mouse button we are holding."""
        for key in list(self._held_keys):
            try: self.kb.release(key)
            except Exception: pass
        for button in list(self._held_mouse):
            try: self.mouse.release(button)
            except Exception: pass
        self._held_keys.clear()
        self._held_mouse.clear()
        self._alt_tab_active = False
        self._move_accum     = [0.0, 0.0]
        self._scroll_accum   = 0.0
        try:
            self.vk.set_shift(False); self.vk.set_altgr(False)
        except (AttributeError, tk.TclError):
            pass

    def _apply_settings(self, ms, ss, dz, ap):
        self.mouse_speed  = float(ms)
        self.scroll_speed = float(ss)
        self.deadzone     = float(dz)
        self.accel_power  = float(ap)

    # ── main tick ──────────────────────────────────────────────────────────

    def tick(self):
        now = time.monotonic()
        try:
            events = pygame.event.get()
        except pygame.error:
            events = []

        if self.js is None:
            if (now >= self._next_connect_try or
                    any(ev.type == PGL.JOYDEVICEADDED for ev in events)):
                self._try_connect(now)
            return

        for ev in events:
            if ev.type == PGL.JOYDEVICEREMOVED and self._is_our_device(ev):
                self._on_disconnect(now)
                return

        lt_on   = self._trigger(AXIS_LT) > TRIGGER_THRESHOLD
        rt_on   = self._trigger(AXIS_RT) > TRIGGER_THRESHOLD
        hat     = self._hat()
        back    = self._btn(BTN_BACK)
        vk_mode = self.vk.is_visible()

        # Triggers: Shift/Ctrl normally, on-screen Shift/AltGr while the
        # keyboard is open. Evaluated every tick in every mode so a modifier
        # can't be left held across a mode change.
        self._set_key(Key.shift, lt_on and not vk_mode)
        self._set_key(Key.ctrl,  rt_on and not vk_mode)
        self.vk.set_shift(lt_on and vk_mode)
        self.vk.set_altgr(rt_on and vk_mode)

        if self._pressed(BTN_BACK):
            self._back_down_at = now
            self._back_chorded = vk_mode   # Back in the VK is Caps Lock, not Esc

        if vk_mode:
            self._vk_tick(hat)
        elif back:
            self._secondary_tick(hat)
        else:
            self._primary_tick(hat)

        if vk_mode or back:
            self._move_accum   = [0.0, 0.0]
            self._scroll_accum = 0.0

        # Mouse buttons are released whenever their button is let go, whatever
        # mode we're in now (e.g. A held, then Back pressed, then A released).
        if MButton.left  in self._held_mouse and not self._btn(BTN_A):
            self._set_mouse(MButton.left,  False)
        if MButton.right in self._held_mouse and not self._btn(BTN_X):
            self._set_mouse(MButton.right, False)

        # Back released: drop Alt from Alt+Tab; a clean short tap = Escape.
        if self._released(BTN_BACK):
            if self._alt_tab_active:
                self._set_key(Key.alt, False)
                self._alt_tab_active = False
            if (not self._back_chorded and not vk_mode
                    and now - self._back_down_at <= BACK_TAP_MAX):
                self._tap(Key.esc)

        for i in range(16):
            self.prev_btn[i] = self._btn(i)
        self.prev_hat = hat

    # ── primary layout ─────────────────────────────────────────────────────

    def _primary_tick(self, hat):
        # mouse movement with acceleration curve
        lx = self._stick(AXIS_LX)
        ly = self._stick(AXIS_LY)
        if lx or ly:
            mag = (lx**2 + ly**2) ** 0.5          # 0..1 stick magnitude
            mag = min(1.0, mag)
            accel = mag ** self.accel_power         # apply power curve
            scale = (accel / mag) if mag > 0 else 0
            # keep the fractional pixels so slow, precise movement still moves
            fx = lx * scale * self.mouse_speed + self._move_accum[0]
            fy = ly * scale * self.mouse_speed + self._move_accum[1]
            mx, my = int(fx), int(fy)
            self._move_accum = [fx - mx, fy - my]
            if mx or my:
                self.mouse.move(mx, my)
        else:
            self._move_accum = [0.0, 0.0]

        # scroll — right stick Y, up=-1 so negate for natural scroll direction
        ry = self._stick(AXIS_RY)
        if abs(ry) < 0.01:
            self._scroll_accum = 0.0
        else:
            delta = -ry * (self.scroll_speed * 0.15)
            if self._scroll_accum * delta < 0:   # direction reversed
                self._scroll_accum = 0.0
            self._scroll_accum += delta
            self._scroll_accum  = max(-10.0, min(10.0, self._scroll_accum))
            steps = int(self._scroll_accum)
            if steps:
                self.mouse.scroll(0, steps)
                self._scroll_accum -= steps

        # buttons (releases are handled in tick())
        if self._pressed(BTN_A): self._set_mouse(MButton.left,  True)
        if self._pressed(BTN_X): self._set_mouse(MButton.right, True)

        if self._pressed(BTN_Y):  self._tap(Key.media_play_pause)
        if self._pressed(BTN_LB): self._tap(Key.media_previous)
        if self._pressed(BTN_RB): self._tap(Key.media_next)

        if self._pressed(BTN_START): self._tap(Key.enter)

        # D-pad → arrow keys
        arrows = {"up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right}
        for d in self._hat_presses(hat):
            self._tap(arrows[d])

        if self._pressed(BTN_LS):
            self.vk_last_dir = (0, 0)
            self.vk.show()

        if self._pressed(BTN_RS):
            self.overlay.toggle()

    # ── secondary layout ───────────────────────────────────────────────────

    def _secondary_tick(self, hat):
        volume = {"up": Key.media_volume_up, "down": Key.media_volume_down,
                  "left": Key.media_volume_mute}
        for d in self._hat_presses(hat):
            if d in volume:
                self._tap(volume[d]); self._back_chorded = True

        if self._pressed(BTN_X):
            self._tap(Key.f5); self._back_chorded = True
        if self._pressed(BTN_Y):
            self._back_chorded = True
            if self._alt_tab_active:        # Alt is already down
                self._tap(Key.f4)
            else:
                self._set_key(Key.alt, True)
                try:     self._tap(Key.f4)
                finally: self._set_key(Key.alt, False)
        if self._pressed(BTN_A):
            self._back_chorded = True
            self.mouse.click(MButton.left, 2)
        # Back + LB = Alt+Tab
        # Alt stays held while Back is held, each LB press taps Tab to cycle windows
        if self._pressed(BTN_LB):
            self._back_chorded = True
            if not self._alt_tab_active:
                self._set_key(Key.alt, True)
                self._alt_tab_active = True
            self._tap(Key.tab)

    # ── virtual keyboard ───────────────────────────────────────────────────

    def _vk_tick(self, hat):
        now = time.monotonic()

        # navigation: d-pad takes priority over stick
        hx, hy = hat
        if hx or hy:
            dx, dy = hx, -hy   # hat up=+1 → grid up=-1
        else:
            lx = self._stick(AXIS_LX)
            ly = self._stick(AXIS_LY)
            dx = (1 if lx > 0.5 else -1 if lx < -0.5 else 0)
            dy = (1 if ly > 0.5 else -1 if ly < -0.5 else 0)

        cur_dir = (dx, dy)
        if cur_dir != (0, 0):
            if cur_dir != self.vk_last_dir:
                self.vk.move(dx, dy)
                self.vk_move_until = now + REPEAT_DELAY
                self.vk_last_dir   = cur_dir
            elif now >= self.vk_move_until:
                self.vk.move(dx, dy)
                self.vk_move_until = now + REPEAT_RATE
        else:
            self.vk_last_dir = (0, 0)

        if self._pressed(BTN_A):     self.vk.type_selected(self.kb)
        if self._pressed(BTN_Y):     self._tap(Key.space)
        if self._pressed(BTN_X):     self._tap(Key.backspace)
        if self._pressed(BTN_B):     self._tap(Key.delete)
        if self._pressed(BTN_RS):    self._tap(Key.tab)
        if self._pressed(BTN_START): self._tap(Key.enter)

        if self._pressed(BTN_LS): self.vk.hide()
        if self._pressed(BTN_BACK): self._tap(Key.caps_lock)

        # LB / RB → shrink / grow keyboard
        if self._pressed(BTN_LB): self.vk.resize(-0.1)
        if self._pressed(BTN_RB): self.vk.resize( 0.1)

    # ── connection ─────────────────────────────────────────────────────────

    def _is_our_device(self, ev):
        iid = getattr(ev, "instance_id", None)
        if iid is None or self.js is None:
            return True
        try:    return iid == self.js.get_instance_id()
        except Exception: return True

    def _on_disconnect(self, now):
        print("[Controller] Disconnected.")
        self.release_all()
        self.js = None
        self.prev_btn = [False] * 16
        self.prev_hat = (0, 0)
        self._back_chorded = False
        self._back_down_at = float("-inf")
        self._next_connect_try = now

    def _try_connect(self, now):
        self._next_connect_try = now + RECONNECT_INTERVAL
        try:
            if pygame.joystick.get_count() == 0:
                # full re-scan as a fallback for drivers that miss hot-plug events
                pygame.joystick.quit()
                pygame.joystick.init()
            if pygame.joystick.get_count() == 0:
                return
            js = pygame.joystick.Joystick(0)
            js.init()
        except pygame.error as e:
            print(f"[Controller] Connect failed: {e}")
            return
        self.js = js
        print(f"[Controller] Connected: {self.js.get_name()}")

        # pump so SDL reports stable values
        for _ in range(10):
            pygame.event.pump()

        print("  Axis layout: LX=0 LY=1 RX=2 RY=3 LT=4 RT=5")

        # force-release any stuck modifiers
        self.release_all()
        for k in (Key.shift, Key.ctrl):
            try: self.kb.release(k)
            except Exception: pass

        # triggers stay ignored until seen at rest or moved (see __init__)
        for ax in (AXIS_LT, AXIS_RT):
            self._trig_armed[ax]   = False
            self._trig_initial[ax] = self._raw(ax)

        # warm up button state
        for i in range(16):
            self.prev_btn[i] = self._btn(i)
        self.prev_hat = self._hat()
        self._back_chorded = False
        self._back_down_at = float("-inf")

    # ── run ────────────────────────────────────────────────────────────────

    def run(self):
        print("Controller Companion started.")
        print("Plug in controller. RS=overlay  LS=keyboard  close window=quit")
        # closing the console window / Ctrl+Break → exit cleanly
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, lambda *_: self.quit())
        clock = pygame.time.Clock()
        try:
            self._try_connect(time.monotonic())
            while self.running:
                try:
                    self.root.update()
                except tk.TclError:
                    break
                self.tick()
                clock.tick(1000 // TICK_MS)
        finally:
            # whatever happened (quit, crash, Ctrl+C), never leave keys held
            self.release_all()
            pygame.quit()
            try:    self.root.destroy()
            except tk.TclError: pass
            print("Goodbye.")

    def quit(self):
        self.running = False


if __name__ == "__main__":
    ControllerCompanion().run()
