"""Themed widgets drawn on canvases: buttons, sliders, toggles, windows."""

import logging
import tkinter as tk
import tkinter.font as tkfont

from .. import win32
from . import theme as T

log = logging.getLogger(__name__)


def style_decorated(win):
    """Dark title bar that matches the window background."""
    try:
        win.update_idletasks()
        win32.style_window(int(win.wm_frame(), 16), caption_hex=T.BG)
    except (tk.TclError, ValueError):
        pass


# ═══════════════════════════════════════════════════════════════════════════
#  BUTTON
# ═══════════════════════════════════════════════════════════════════════════

_BUTTON_KINDS = {
    #            normal         hover          pressed        text
    "primary":   (T.ACCENT,     T.ACCENT_HI,   T.ACCENT_LO,   T.ON_ACCENT),
    "secondary": (T.SURFACE_HI, T.SURFACE_HOV, T.SURFACE,     T.TEXT),
    "ghost":     (None,         T.SURFACE_HI,  T.SURFACE,     T.MUTED),
}


class Button(tk.Canvas):
    def __init__(self, parent, text, command=None, kind="secondary",
                 width=None, height=34, icon=""):
        self._command = command
        self._kind    = kind
        self._font    = T.font(10, "semibold")
        self._fixed_w = T.px(width) if width else None
        self._h       = T.px(height)
        self._hover = self._down = False
        super().__init__(parent, height=self._h, bg=parent["bg"],
                         highlightthickness=0, bd=0, cursor="hand2")
        self._bg  = self.create_image(0, 0, anchor="nw")
        self._txt = self.create_text(0, 0, font=self._font)
        self.set_text(text, icon)
        self.bind("<Enter>",           lambda e: self._state(hover=True))
        self.bind("<Leave>",           lambda e: self._state(hover=False, down=False))
        self.bind("<ButtonPress-1>",   lambda e: self._state(down=True))
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Configure>",       lambda e: self._paint())

    def set_text(self, text, icon=""):
        label = f"{icon}  {text}" if icon else text
        self.itemconfig(self._txt, text=label)
        w = self._fixed_w or tkfont.Font(font=self._font).measure(label) + T.px(32)
        self.configure(width=w)
        self._paint()

    def set_kind(self, kind):
        self._kind = kind
        self._paint()

    def _state(self, hover=None, down=None):
        if hover is not None: self._hover = hover
        if down  is not None: self._down  = down
        self._paint()

    def _release(self, e):
        fire = self._down and self._hover
        self._state(down=False)
        if fire and self._command:
            self._command()

    def _paint(self):
        w = self.winfo_width() if self.winfo_width() > 1 else int(self["width"])
        normal, hover, pressed, fg = _BUTTON_KINDS[self._kind]
        fill = pressed if self._down else hover if self._hover else normal
        if fill:
            self.itemconfig(self._bg, image=T.rrect(w, self._h, T.px(8), fill), state="normal")
        else:
            self.itemconfig(self._bg, state="hidden")
        self.itemconfig(self._txt, fill=T.TEXT if (self._kind == "ghost" and self._hover) else fg)
        self.coords(self._txt, w / 2, self._h / 2)


# ═══════════════════════════════════════════════════════════════════════════
#  SLIDER
# ═══════════════════════════════════════════════════════════════════════════

class Slider(tk.Canvas):
    """Filled track + round knob. Drag, click, mouse wheel or arrow keys."""

    def __init__(self, parent, from_, to, step, value, command=None):
        self.from_, self.to, self.step = from_, to, step
        self._value   = value
        self._command = command
        self._hover   = self._drag = False
        self._knob_d  = T.px(18)
        self._pad     = self._knob_d // 2 + T.px(3)
        h = self._knob_d + T.px(8)
        super().__init__(parent, height=h, bg=parent["bg"], highlightthickness=0,
                         bd=0, cursor="hand2", takefocus=1, width=T.px(260))
        y = h / 2
        tw = T.px(6)
        self._track = self.create_line(0, y, 0, y, fill=T.TRACK, width=tw, capstyle="round")
        self._fill  = self.create_line(0, y, 0, y, fill=T.ACCENT, width=tw, capstyle="round")
        self._knob  = self.create_image(0, y)
        self.bind("<Configure>",       lambda e: self._paint())
        self.bind("<Enter>",           lambda e: self._set_hover(True))
        self.bind("<Leave>",           lambda e: self._set_hover(False))
        self.bind("<ButtonPress-1>",   self._on_press)
        self.bind("<B1-Motion>",       lambda e: self._set_from_x(e.x))
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<MouseWheel>",      lambda e: self._nudge(1 if e.delta > 0 else -1))
        self.bind("<Left>",            lambda e: self._nudge(-1))
        self.bind("<Right>",           lambda e: self._nudge(1))

    def get(self):
        return self._value

    def set(self, value, notify=False):
        value = max(self.from_, min(self.to, value))
        value = self.from_ + round((value - self.from_) / self.step) * self.step
        value = round(value, 6)
        changed = value != self._value
        self._value = value
        self._paint()
        if notify and changed and self._command:
            self._command(value)

    def _x_bounds(self):
        w = max(self.winfo_width(), int(self["width"]))
        return self._pad, w - self._pad

    def _paint(self):
        x0, x1 = self._x_bounds()
        frac = (self._value - self.from_) / (self.to - self.from_)
        x = x0 + frac * (x1 - x0)
        y = int(self["height"]) / 2
        self.coords(self._track, x0, y, x1, y)
        self.coords(self._fill,  x0, y, x, y)
        self.itemconfig(self._fill, state="normal" if x > x0 + 1 else "hidden")
        d = self._knob_d + (T.px(2) if (self._hover or self._drag) else 0)
        self.itemconfig(self._knob, image=T.circle(d, T.TEXT, T.ACCENT, max(2, T.px(3))))
        self.coords(self._knob, x, y)

    def _set_from_x(self, x):
        x0, x1 = self._x_bounds()
        frac = max(0.0, min(1.0, (x - x0) / max(1, x1 - x0)))
        self.set(self.from_ + frac * (self.to - self.from_), notify=True)

    def _nudge(self, n):
        self.set(self._value + n * self.step, notify=True)

    def _set_hover(self, on):
        self._hover = on
        self._paint()

    def _on_press(self, e):
        self.focus_set()
        self._drag = True
        self._set_from_x(e.x)

    def _on_release(self, e):
        self._drag = False
        self._paint()


# ═══════════════════════════════════════════════════════════════════════════
#  TOGGLE SWITCH
# ═══════════════════════════════════════════════════════════════════════════

class Toggle(tk.Canvas):
    def __init__(self, parent, value=False, command=None):
        self._value, self._command = value, command
        self._tw, self._th = T.px(40), T.px(22)
        super().__init__(parent, width=self._tw, height=self._th, bg=parent["bg"],
                         highlightthickness=0, bd=0, cursor="hand2")
        self._track = self.create_image(0, 0, anchor="nw")
        self._knob  = self.create_image(0, 0)
        self.bind("<ButtonRelease-1>", lambda e: self.set(not self._value, notify=True))
        self._paint()

    def get(self):
        return self._value

    def set(self, value, notify=False):
        self._value = bool(value)
        self._paint()
        if notify and self._command:
            self._command(self._value)

    def _paint(self):
        on = self._value
        self.itemconfig(self._track, image=T.rrect(self._tw, self._th, self._th // 2,
                                                   T.ACCENT if on else T.TRACK))
        d = self._th - T.px(6)
        self.itemconfig(self._knob, image=T.circle(d, T.ON_ACCENT if on else T.MUTED))
        x = self._tw - self._th / 2 if on else self._th / 2
        self.coords(self._knob, x, self._th / 2)


# ═══════════════════════════════════════════════════════════════════════════
#  FLOATING WINDOW THAT NEVER TAKES FOCUS
# ═══════════════════════════════════════════════════════════════════════════
#
# Tk's deiconify() activates the window, stealing keyboard focus from the app
# you're typing into. Instead, the native window is created once, marked
# WS_EX_NOACTIVATE, and shown/hidden with ShowWindow(SW_SHOWNOACTIVATE), so
# the foreground window never changes, not even when it is clicked.

class FloatingWindow:
    def __init__(self, root, title, alpha=None):
        self.win = tk.Toplevel(root)
        self.win.title(title)
        self.win.configure(bg=T.BG)
        self.win.resizable(False, False)
        self.win.overrideredirect(True)      # borderless HUD
        self.win.attributes("-topmost", True)
        if alpha is not None:
            self.win.attributes("-alpha", alpha)
        self._visible = False
        self._hwnd    = None

    def realize(self):
        """Call once after the window's contents are built."""
        if win32.IS_WINDOWS:
            try:
                # Map once off-screen so Tk creates the native window.
                self.win.geometry("+-32000+-32000")
                self.win.update_idletasks()
                self.win.update()
                hwnd = int(self.win.wm_frame(), 16)
                win32.hide_window(hwnd)
                win32.make_no_activate(hwnd)
                # clicks land on child windows (e.g. the canvas), so cover them all
                for w in [self.win, *self._descendants(self.win)]:
                    win32.block_mouse_activate(w.winfo_id())
                win32.block_mouse_activate(hwnd)
                win32.style_window(hwnd)     # rounded corners on Windows 11
                self._hwnd = hwnd
                return
            except Exception as e:
                log.warning("No-activate window setup failed, falling back: %s", e)
        self.win.withdraw()

    @classmethod
    def _descendants(cls, w):
        for child in w.winfo_children():
            yield child
            yield from cls._descendants(child)

    def _place(self, fx, fy, margin):
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        area = win32.work_area() or (0, 0, self.win.winfo_screenwidth(),
                                     self.win.winfo_screenheight())
        l, t, r, b = area
        x = l + int((r - l - w) * fx)
        y = t + int((b - t - h) * fy)
        y = max(t, min(y, b - h - margin))
        self.win.geometry(f"+{x}+{y}")
        # Apply the move now: Tk defers it to idle time, and a ShowWindow in
        # between would make Tk re-read (and keep) the old position.
        self.win.update_idletasks()

    def place_bottom_center(self, margin=None):
        self._place(0.5, 1.0, T.px(24) if margin is None else margin)

    def place_center(self):
        self._place(0.5, 0.45, 0)

    def show(self):
        if self._hwnd:
            win32.show_no_activate(self._hwnd)
        else:
            self.win.deiconify(); self.win.lift()
        self._visible = True

    def hide(self):
        if self._hwnd:
            win32.hide_window(self._hwnd)
        else:
            self.win.withdraw()
        self._visible = False

    def toggle(self):
        self.hide() if self._visible else self.show()

    def is_visible(self):
        return self._visible
