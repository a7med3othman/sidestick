"""Settings window. Changes apply live and are saved automatically."""

import tkinter as tk

from .. import config as C
from .. import win32
from . import theme as T
from .widgets import Button, Slider, Toggle, style_decorated

CARD_WIDTH = 380

POINTER = (
    # field,        title,                     description,                                 min,  max, step, format
    ("mouse_speed", "Pointer speed",           "How fast the cursor moves at full tilt",    1,    60,  1,    lambda v: f"{v:.0f}"),
    ("accel_power", "Acceleration",            "Higher gives finer control near the centre", 1.0, 4.0, 0.1,  lambda v: "Linear" if v < 1.05 else f"{v:.1f}×"),
    ("precision",   "Precision mode (hold B)", "Cursor speed while B is held",              0.1,  1.0, 0.05, lambda v: f"{v * 100:.0f}%"),
    ("deadzone",    "Stick dead-zone",         "Ignore stick movement smaller than this",   0.0,  0.5, 0.01, lambda v: f"{v:.2f}"),
)
SCROLL = (
    ("scroll_speed", "Scroll speed",           "How fast the right stick scrolls",          1,    20,  1,    lambda v: f"{v:.0f}"),
)


class Card(tk.Canvas):
    """A rounded surface; put widgets in `.body`."""

    def __init__(self, parent, title=None, pad=16):
        super().__init__(parent, bg=parent["bg"], highlightthickness=0, bd=0,
                         width=T.px(CARD_WIDTH), height=T.px(40))
        self._pad = p = T.px(pad)
        self._img = self.create_image(0, 0, anchor="nw")
        self.body = tk.Frame(self, bg=T.SURFACE)
        self.body.columnconfigure(0, weight=1)
        self._win = self.create_window(p, p, window=self.body, anchor="nw")
        if title:
            tk.Label(self.body, text=title, bg=T.SURFACE, fg=T.HEADER,
                     font=T.font(8, "bold")).grid(row=0, column=0, columnspan=2,
                                                  sticky="w", pady=(0, T.px(6)))
        self.body.bind("<Configure>", lambda e: self._fit())
        self.bind("<Configure>", lambda e: self._fit())

    def _fit(self):
        w = max(self.winfo_width(), int(self["width"]))
        self.itemconfig(self._win, width=w - 2 * self._pad)
        h = self.body.winfo_reqheight() + 2 * self._pad
        if int(self["height"]) != h:
            self.configure(height=h)
        self.itemconfig(self._img, image=T.rrect(w, h, T.px(12), T.SURFACE))


class SettingsWindow:

    def __init__(self, root, settings, on_change, on_restart_admin):
        self.settings         = settings
        self.on_change        = on_change
        self.on_restart_admin = on_restart_admin
        self._sliders  = {}
        self._status_job = None
        self._placed     = False

        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.title("Settings: Sidestick")
        self.win.configure(bg=T.BG)
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self.hide)
        self._build()

    # ── layout ─────────────────────────────────────────────────────────────

    def _build(self):
        outer = tk.Frame(self.win, bg=T.BG, padx=T.px(20), pady=T.px(18))
        outer.pack(fill="both", expand=True)

        tk.Label(outer, text="Settings", bg=T.BG, fg=T.TEXT,
                 font=T.font(16, "semibold")).pack(anchor="w")
        tk.Label(outer, text="Changes apply instantly and are saved automatically.",
                 bg=T.BG, fg=T.DIM, font=T.font(9)).pack(anchor="w", pady=(0, T.px(12)))

        cols = tk.Frame(outer, bg=T.BG)
        cols.pack(fill="x")
        left  = tk.Frame(cols, bg=T.BG)
        right = tk.Frame(cols, bg=T.BG)
        left.pack(side="left", fill="y", anchor="n")
        right.pack(side="left", fill="y", anchor="n", padx=(T.px(12), 0))

        card = Card(left, "POINTER")
        card.pack(fill="x")
        for i, spec in enumerate(POINTER):
            self._slider_row(card.body, 1 + i * 3, spec)

        card = Card(right, "SCROLLING")
        card.pack(fill="x")
        self._slider_row(card.body, 1, SCROLL[0])

        card = Card(right, "GENERAL")
        card.pack(fill="x", pady=(T.px(12), 0))
        self._startup = self._toggle_row(
            card.body, 1, "Start with Windows", "Launch in the tray when you sign in",
            win32.get_startup(C.APP_ID), self._set_startup)
        self._minimized = self._toggle_row(
            card.body, 3, "Start minimised to tray", "Don't show this window on launch",
            self.settings.start_minimized, self._set_minimized)
        self._admin_row(card.body, 5)

        footer = tk.Frame(outer, bg=T.BG)
        footer.pack(fill="x", pady=(T.px(16), 0))
        Button(footer, "Reset to defaults", self._reset, kind="ghost").pack(side="left")
        Button(footer, "Done", self.hide, kind="primary", width=96).pack(side="right")
        self._status = tk.Label(footer, text="", bg=T.BG, fg=T.OK, font=T.font(9))
        self._status.pack(side="right", padx=T.px(12))

    def _slider_row(self, parent, row, spec):
        field, title, desc, lo, hi, step, fmt = spec
        top = T.px(10) if row > 1 else 0
        tk.Label(parent, text=title, bg=T.SURFACE, fg=T.TEXT,
                 font=T.font(10, "semibold")).grid(row=row, column=0, sticky="w", pady=(top, 0))
        value = tk.Label(parent, bg=T.SURFACE, fg=T.ACCENT, font=T.font(10, "semibold"))
        value.grid(row=row, column=1, sticky="e", pady=(top, 0))
        tk.Label(parent, text=desc, bg=T.SURFACE, fg=T.DIM,
                 font=T.font(9)).grid(row=row + 1, column=0, columnspan=2, sticky="w")

        def changed(v, field=field, value=value, fmt=fmt):
            value.config(text=fmt(v))
            setattr(self.settings, field, v)
            self._changed()
        slider = Slider(parent, lo, hi, step, getattr(self.settings, field), changed)
        slider.grid(row=row + 2, column=0, columnspan=2, sticky="ew", pady=(T.px(2), 0))
        value.config(text=fmt(slider.get()))
        self._sliders[field] = (slider, value, fmt)

    def _toggle_row(self, parent, row, title, desc, value, command):
        top = T.px(10) if row > 1 else 0
        tk.Label(parent, text=title, bg=T.SURFACE, fg=T.TEXT,
                 font=T.font(10, "semibold")).grid(row=row, column=0, sticky="w", pady=(top, 0))
        tk.Label(parent, text=desc, bg=T.SURFACE, fg=T.DIM,
                 font=T.font(9)).grid(row=row + 1, column=0, sticky="w")
        t = Toggle(parent, value, command)
        t.grid(row=row, column=1, rowspan=2, sticky="e", pady=(top, 0))
        return t

    def _admin_row(self, parent, row):
        top = T.px(12)
        if win32.is_admin():
            tk.Label(parent, text="✓  Running as administrator", bg=T.SURFACE, fg=T.OK,
                     font=T.font(10, "semibold")).grid(row=row, column=0, sticky="w", pady=(top, 0))
            tk.Label(parent, text="The controller works in every app, including admin ones.",
                     bg=T.SURFACE, fg=T.DIM, font=T.font(9)).grid(row=row + 1, column=0, sticky="w")
            return
        tk.Label(parent, text="Administrator apps", bg=T.SURFACE, fg=T.TEXT,
                 font=T.font(10, "semibold")).grid(row=row, column=0, sticky="w", pady=(top, 0))
        tk.Label(parent, text="Windows blocks input to apps running as admin "
                              "(Task Manager, installers) unless this app is too.",
                 bg=T.SURFACE, fg=T.DIM, font=T.font(9), justify="left",
                 wraplength=T.px(CARD_WIDTH - 40)).grid(
                     row=row + 1, column=0, columnspan=2, sticky="w")
        Button(parent, "Restart as admin", self.on_restart_admin, height=30).grid(
            row=row + 2, column=0, columnspan=2, sticky="w", pady=(T.px(8), 0))

    # ── behaviour ──────────────────────────────────────────────────────────

    def _changed(self, message="✓  Saved"):
        self.on_change()
        self._status.config(text=message, fg=T.OK)
        if self._status_job:
            self.win.after_cancel(self._status_job)
        self._status_job = self.win.after(1500, lambda: self._status.config(text=""))

    def _reset(self):
        defaults = C.Settings()
        for field, (slider, value, fmt) in self._sliders.items():
            v = getattr(defaults, field)
            setattr(self.settings, field, v)
            slider.set(v)
            value.config(text=fmt(v))
        self._changed("✓  Defaults restored")

    def _set_startup(self, on):
        try:
            win32.set_startup(C.APP_ID, on)
            self._changed("✓  Saved")
        except OSError as e:
            self._startup.set(not on)
            self._status.config(text=f"Couldn't change startup: {e}", fg=T.BAD)

    def _set_minimized(self, on):
        self.settings.start_minimized = on
        self._changed()

    def refresh(self):
        """Pull values back from settings (e.g. after an external change)."""
        for field, (slider, value, fmt) in self._sliders.items():
            slider.set(getattr(self.settings, field))
            value.config(text=fmt(slider.get()))
        self._minimized.set(self.settings.start_minimized)
        self._startup.set(win32.get_startup(C.APP_ID))

    def show(self):
        self.refresh()
        if not self._placed:
            self._placed = True
            self.win.update_idletasks()
            w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
            x = (self.win.winfo_screenwidth() - w) // 2
            y = max(0, (self.win.winfo_screenheight() - h) // 2 - T.px(40))
            self.win.geometry(f"+{x}+{y}")
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        style_decorated(self.win)

    def hide(self):
        self.win.withdraw()

    def toggle(self):
        if self.win.state() == "withdrawn":
            self.show()
        else:
            self.hide()
