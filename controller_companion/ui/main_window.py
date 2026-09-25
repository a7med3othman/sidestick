"""The small main window: status, pause, and shortcuts to the other windows."""

import tkinter as tk

from PIL import ImageTk

from .. import config as C
from ..icon import make_icon
from . import theme as T
from .widgets import Button, style_decorated

WIDTH = 360


class MainWindow:

    def __init__(self, root, on_close, on_pause, on_overlay, on_keyboard, on_settings):
        self.root = root
        root.title(C.APP_NAME)
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", on_close)
        self._icons = {p: ImageTk.PhotoImage(make_icon(64, paused=p)) for p in (False, True)}
        self._logo  = {p: ImageTk.PhotoImage(make_icon(T.px(44), paused=p)) for p in (False, True)}
        root.iconphoto(True, self._icons[False])

        outer = tk.Frame(root, bg=T.BG, padx=T.px(20), pady=T.px(18))
        outer.pack(fill="both", expand=True)

        head = tk.Frame(outer, bg=T.BG)
        head.pack(fill="x")
        self._logo_lbl = tk.Label(head, image=self._logo[False], bg=T.BG)
        self._logo_lbl.pack(side="left")
        text = tk.Frame(head, bg=T.BG)
        text.pack(side="left", padx=(T.px(12), 0))
        tk.Label(text, text=C.APP_NAME, bg=T.BG, fg=T.TEXT,
                 font=T.font(13, "semibold")).pack(anchor="w")
        status = tk.Frame(text, bg=T.BG)
        status.pack(anchor="w")
        self._dot = tk.Canvas(status, width=T.px(10), height=T.px(10), bg=T.BG,
                              highlightthickness=0, bd=0)
        self._dot_img = self._dot.create_image(T.px(5), T.px(5))
        self._dot.pack(side="left", pady=(T.px(2), 0))
        self._status = tk.Label(status, bg=T.BG, fg=T.MUTED, font=T.font(9))
        self._status.pack(side="left", padx=(T.px(6), 0))

        inner_w = WIDTH - 40
        self._pause = Button(outer, "Pause", on_pause, kind="primary",
                             width=inner_w, height=40)
        self._pause.pack(pady=(T.px(16), T.px(8)))

        row = tk.Frame(outer, bg=T.BG)
        row.pack(fill="x")
        bw = (inner_w - 16) // 3
        for i, (label, cmd) in enumerate((("Bindings", on_overlay),
                                          ("Keyboard", on_keyboard),
                                          ("Settings", on_settings))):
            Button(row, label, cmd, width=bw).pack(side="left", padx=(0 if i == 0 else T.px(8), 0))

        tk.Label(outer, text="Hold Back + Start for 1 second to pause.\n"
                             "Closing this window keeps it running in the tray.",
                 bg=T.BG, fg=T.DIM, font=T.font(8), justify="left").pack(
                     anchor="w", pady=(T.px(14), 0))

        self.set_state(None, False)

    def set_state(self, controller, paused, error=None):
        if error:
            color, text = T.BAD, error
        elif paused:
            color, text = T.WARN, "Paused. Hold Back + Start to resume"
        elif controller:
            color, text = T.OK, f"Connected · {controller}"
        else:
            color, text = T.DIM, "Waiting for a controller…"
        if len(text) > 44:
            text = text[:43] + "…"
        self._status.config(text=text)
        self._dot.itemconfig(self._dot_img, image=T.circle(T.px(8), color))
        self._pause.set_text("Resume" if paused else "Pause")
        self._pause.set_kind("secondary" if paused else "primary")
        self._logo_lbl.config(image=self._logo[paused])
        self.root.iconphoto(True, self._icons[paused])

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        style_decorated(self.root)

    def hide(self):
        self.root.withdraw()
