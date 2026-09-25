#!/usr/bin/env python3
"""
Controller Companion — Xbox Series X gamepad → mouse + keyboard
Requirements: pip install pygame pynput pillow
Usage:        python controller_companion.py
"""

import time
import tkinter as tk

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
        def on_change(v, lbl=val_lbl, f=fmt, u=unit):
            lbl.config(text=f(float(v))+(" "+u if u else ""))
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

    def _reset(self):
        self._mouse_var.set(18); self._scroll_var.set(5)
        self._dz_var.set(0.15); self._accel_var.set(2.0)
        self._apply_live()
        self._status.config(text="✓ Reset to defaults")
        self.win.after(1500, lambda: self._status.config(text=""))

    def show(self):
        ms, ss, dz, ap = self._get()
        self._mouse_var.set(ms); self._scroll_var.set(ss)
        self._dz_var.set(dz);    self._accel_var.set(ap)
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
    win = tk.Toplevel(root)
    win.title("Controller Companion – Bindings")
    win.configure(bg=BG)
    win.attributes("-topmost", True)
    win.attributes("-alpha", 0.93)
    win.resizable(False, False)
    win.protocol("WM_DELETE_WINDOW", win.withdraw)
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
    win.withdraw()
    return win

# ═══════════════════════════════════════════════════════════════════════════
#  VIRTUAL KEYBOARD WINDOW
# ═══════════════════════════════════════════════════════════════════════════

class VirtualKeyboard:
    def __init__(self, root):
        self.root = root
        self.win  = tk.Toplevel(root)
        self.win.title("Virtual Keyboard")
        self.win.configure(bg=BG)
        self.win.attributes("-topmost", True)
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self.hide)
        self._visible  = False
        self.row       = 0
        self.col       = 0
        self.shift_on  = False
        self.altgr_on  = False
        self._scale    = 1.0   # 0.5 = small .. 2.5 = large
        self._build()
        self.win.withdraw()

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

    def _get_foreground_hwnd(self):
        """Get the HWND of whichever window currently has focus."""
        try:
            import ctypes
            return ctypes.windll.user32.GetForegroundWindow()
        except Exception:
            return None

    def _restore_focus(self, hwnd):
        """Give focus back to a previously active window."""
        if not hwnd:
            return
        try:
            import ctypes
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def move(self, dx, dy):
        nr = max(0, min(VK_ROWS_N-1, self.row + dy))
        nc = max(0, min(len(VK_ROWS[nr])-1, self.col + dx))
        if nr != self.row or nc != self.col:
            self.row, self.col = nr, nc
            self._highlight()

    def type_selected(self, kb):
        char = vk_char(self.row, self.col, self.shift_on)
        if self.altgr_on: kb.press(Key.alt_gr)
        kb.press(KeyCode.from_char(char))
        kb.release(KeyCode.from_char(char))
        if self.altgr_on: kb.release(Key.alt_gr)

    def set_shift(self, on):
        self.shift_on = on
        self._refresh_mod()
        for r, row in enumerate(self.cells):
            for c, cell in enumerate(row):
                cell.config(text=vk_display(r, c, on))
        self._highlight()

    def set_altgr(self, on):
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
        self._size_lbl.config(text=f"{int(self._scale*100)}%")
        try:
            self.win.update_idletasks()
            sw = self.win.winfo_screenwidth()
            sh = self.win.winfo_screenheight()
            nw = self.win.winfo_width()
            nh = self.win.winfo_height()
            x  = (sw - nw) // 2
            y  = max(0, sh - nh - 60)
            self.win.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def show(self):
        # Remember who has focus RIGHT NOW before we steal it
        prev_hwnd = self._get_foreground_hwnd()
        # Show the keyboard
        self.win.deiconify()
        self.win.attributes("-topmost", True)
        self.win.update_idletasks()
        # Position at bottom centre
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        w  = self.win.winfo_width()
        h  = self.win.winfo_height()
        x  = (sw - w) // 2
        y  = sh - h - 60
        self.win.geometry(f"+{x}+{y}")
        self._visible = True
        # Immediately give focus back to whatever had it before
        self.win.after(10, lambda: self._restore_focus(prev_hwnd))

    def hide(self):
        self.win.withdraw()
        self._visible = False

    def is_visible(self): return self._visible

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

        # live sensitivity
        self.mouse_speed  = float(MOUSE_SPEED)
        self.scroll_speed = float(SCROLL_SPEED)
        self.deadzone     = float(DEADZONE)
        self.accel_power  = float(ACCEL_POWER)

        # button/hat state
        self.prev_btn  = [False] * 16
        self.prev_hat  = (0, 0)
        self.back_held      = False
        self.lt_held        = False
        self.rt_held        = False
        self._alt_tab_active = False

        # scroll accumulator
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
        except: return 0.0

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
        # remap -1..+1 → 0..1
        return (raw + 1.0) / 2.0

    def _hat(self):
        try:    return self.js.get_hat(HAT_IDX)
        except: return (0, 0)

    def _btn(self, i):
        try:    return bool(self.js.get_button(i))
        except: return False

    def _pressed(self, i):  return self._btn(i) and not self.prev_btn[i]
    def _released(self, i): return not self._btn(i) and self.prev_btn[i]

    def _tap(self, key):
        self.kb.press(key); self.kb.release(key)

    def _apply_settings(self, ms, ss, dz, ap):
        self.mouse_speed  = float(ms)
        self.scroll_speed = float(ss)
        self.deadzone     = float(dz)
        self.accel_power  = float(ap)

    # ── main tick ──────────────────────────────────────────────────────────

    def tick(self):
        if self.js is None:
            self._try_connect()
            return

        try:
            events = pygame.event.get()
        except Exception:
            return

        for ev in events:
            if ev.type == PGL.JOYDEVICEREMOVED:
                print("[Controller] Disconnected.")
                self.js = None
                return

        lt_on = self._trigger(AXIS_LT) > TRIGGER_THRESHOLD
        rt_on = self._trigger(AXIS_RT) > TRIGGER_THRESHOLD
        hat   = self._hat()
        back  = self._btn(BTN_BACK)

        if self.vk.is_visible():
            self._vk_tick(lt_on, rt_on, hat)
        elif back:
            self._secondary_tick(hat)
        else:
            self._primary_tick(lt_on, rt_on)

        for i in range(16):
            self.prev_btn[i] = self._btn(i)
        self.prev_hat  = hat
        # Track Back release to drop Alt if it was held for Alt+Tab
        if self.back_held and not back:
            if self._alt_tab_active:
                self.kb.release(Key.alt)
                self._alt_tab_active = False
        self.back_held = back

    # ── primary layout ─────────────────────────────────────────────────────

    def _primary_tick(self, lt_on, rt_on):
        # mouse movement with acceleration curve
        lx = self._stick(AXIS_LX)
        ly = self._stick(AXIS_LY)
        if lx or ly:
            mag = (lx**2 + ly**2) ** 0.5          # 0..1 stick magnitude
            mag = min(1.0, mag)
            accel = mag ** self.accel_power         # apply power curve
            scale = (accel / mag) if mag > 0 else 0
            mx = int(lx * scale * self.mouse_speed)
            my = int(ly * scale * self.mouse_speed)
            if mx or my:
                self.mouse.move(mx, my)

        # scroll — right stick Y, up=-1 so negate for natural scroll direction
        ry = self._stick(AXIS_RY)
        if abs(ry) < 0.01:
            self._scroll_accum = 0.0
        else:
            self._scroll_accum += -ry * (self.scroll_speed * 0.15)
            self._scroll_accum  = max(-10.0, min(10.0, self._scroll_accum))
            steps = int(self._scroll_accum)
            if steps:
                self.mouse.scroll(0, steps)
                self._scroll_accum -= steps

        # buttons
        if self._pressed(BTN_A):  self.mouse.press(MButton.left)
        if self._released(BTN_A): self.mouse.release(MButton.left)

        if self._pressed(BTN_X):  self.mouse.press(MButton.right)
        if self._released(BTN_X): self.mouse.release(MButton.right)

        if self._pressed(BTN_Y):  self._tap(Key.media_play_pause)
        if self._pressed(BTN_LB): self._tap(Key.media_previous)
        if self._pressed(BTN_RB): self._tap(Key.media_next)

        if lt_on and not self.lt_held:
            self.kb.press(Key.shift);   self.lt_held = True
        elif not lt_on and self.lt_held:
            self.kb.release(Key.shift); self.lt_held = False

        if rt_on and not self.rt_held:
            self.kb.press(Key.ctrl);    self.rt_held = True
        elif not rt_on and self.rt_held:
            self.kb.release(Key.ctrl);  self.rt_held = False

        if self._pressed(BTN_START): self._tap(Key.enter)

        if self._released(BTN_BACK) and not self.back_held:
            self._tap(Key.esc)

        # D-pad → arrow keys
        hat = self._hat()
        if hat != self.prev_hat:
            hx, hy = hat
            if   hy ==  1: self._tap(Key.up)
            elif hy == -1: self._tap(Key.down)
            elif hx == -1: self._tap(Key.left)
            elif hx ==  1: self._tap(Key.right)

        if self._pressed(BTN_LS): self.vk.show()

        if self._pressed(BTN_RS):
            if self.overlay.state() == "withdrawn":
                self.overlay.deiconify(); self.overlay.lift()
            else:
                self.overlay.withdraw()

    # ── secondary layout ───────────────────────────────────────────────────

    def _secondary_tick(self, hat):
        if hat != self.prev_hat:
            hx, hy = hat
            if   hy ==  1: self._tap(Key.media_volume_up)
            elif hy == -1: self._tap(Key.media_volume_down)
            elif hx == -1: self._tap(Key.media_volume_mute)

        if self._pressed(BTN_X): self._tap(Key.f5)
        if self._pressed(BTN_Y):
            self.kb.press(Key.alt); self._tap(Key.f4); self.kb.release(Key.alt)
        if self._pressed(BTN_A):
            self.mouse.click(MButton.left, 2)
        # Back + LB = Alt+Tab
        # Alt stays held while Back is held, each LB press taps Tab to cycle windows
        if self._pressed(BTN_LB):
            if not self._alt_tab_active:
                self.kb.press(Key.alt)
                self._alt_tab_active = True
            self._tap(Key.tab)

    # ── virtual keyboard ───────────────────────────────────────────────────

    def _vk_tick(self, lt_on, rt_on, hat):
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
        if self._pressed(BTN_RS):     self._tap(Key.tab)
        if self._pressed(BTN_START): self._tap(Key.enter)

        if lt_on and not self.lt_held:
            self.lt_held = True;  self.vk.set_shift(True)
        elif not lt_on and self.lt_held:
            self.lt_held = False; self.vk.set_shift(False)

        if rt_on and not self.rt_held:
            self.rt_held = True;  self.vk.set_altgr(True)
        elif not rt_on and self.rt_held:
            self.rt_held = False; self.vk.set_altgr(False)

        if self._pressed(BTN_LS): self.vk.hide()
        if self._pressed(BTN_BACK): self._tap(Key.caps_lock)

        # LB / RB → shrink / grow keyboard
        if self._pressed(BTN_LB): self.vk.resize(-0.1)
        if self._pressed(BTN_RB): self.vk.resize( 0.1)

    # ── connection ─────────────────────────────────────────────────────────

    def _try_connect(self):
        pygame.joystick.quit()
        pygame.joystick.init()
        if pygame.joystick.get_count() == 0:
            return
        self.js = pygame.joystick.Joystick(0)
        self.js.init()
        print(f"[Controller] Connected: {self.js.get_name()}")

        # pump so SDL reports stable values
        for _ in range(10):
            pygame.event.pump()

        print("  Axis layout: LX=0 LY=1 RX=2 RY=3 LT=4 RT=5")

        # force-release any stuck modifiers
        for k in (Key.shift, Key.ctrl):
            try: self.kb.release(k)
            except: pass
        self.lt_held = self.rt_held = False

        # warm up button state
        for i in range(16):
            try:    self.prev_btn[i] = bool(self.js.get_button(i))
            except: self.prev_btn[i] = False

    # ── run ────────────────────────────────────────────────────────────────

    def run(self):
        print("Controller Companion started.")
        print("Plug in controller. RS=overlay  LS=keyboard  close window=quit")
        self._try_connect()
        clock = pygame.time.Clock()
        while self.running:
            try:
                self.root.update()
            except tk.TclError:
                break
            self.tick()
            clock.tick(1000 // TICK_MS)
        pygame.quit()
        print("Goodbye.")

    def quit(self):
        self.running = False


if __name__ == "__main__":
    ControllerCompanion().run()
