"""Bindings overlay: a floating, glanceable cheat sheet (RS click)."""

import tkinter as tk
import tkinter.font as tkfont

from . import theme as T
from .widgets import FloatingWindow

BINDINGS = (
    ("MOUSE & MEDIA", (
        ("Left stick",  "Move cursor"),
        ("B  hold",     "Precision cursor"),
        ("Right stick", "Scroll  ↕ ↔"),
        ("A",           "Left click / drag"),
        ("X",           "Right click"),
        ("Y",           "Play / pause"),
        ("LB / RB",     "Previous / next track"),
        ("LT  hold",    "Shift"),
        ("RT  hold",    "Ctrl"),
        ("D-pad",       "Arrow keys"),
        ("Start",       "Enter"),
        ("Back  tap",   "Escape"),
        ("LS click",    "On-screen keyboard"),
        ("RS click",    "This overlay"),
    )),
    ("HOLD BACK  +", (
        ("D-pad ↑ / ↓", "Volume up / down"),
        ("D-pad ←",     "Mute"),
        ("A",           "Double click"),
        ("X",           "Refresh  (F5)"),
        ("Y",           "Close window  (Alt+F4)"),
        ("LB",          "Switch window  (Alt+Tab)"),
        ("Start  1 s",  "Pause / resume"),
    )),
    ("KEYBOARD OPEN", (
        ("Stick / D-pad", "Move selection"),
        ("A",             "Press key"),
        ("Y",             "Space"),
        ("X",             "Backspace"),
        ("B",             "Delete"),
        ("Start",         "Enter"),
        ("RS click",      "Tab"),
        ("LT  hold",      "Shift"),
        ("RT  hold",      "AltGr"),
        ("Back",          "Caps Lock"),
        ("LB / RB",       "Smaller / bigger"),
        ("LS click",      "Close"),
    )),
)


class Overlay(FloatingWindow):

    def __init__(self, root):
        super().__init__(root, "Sidestick: Bindings")
        cv = tk.Canvas(self.win, bg=T.BG, highlightthickness=0, bd=0)
        cv.pack()
        self._draw(cv)
        self.realize()
        self.place_center()

    def _draw(self, cv):
        pad, gap = T.px(22), T.px(12)
        badge_f = T.font(9, "semibold")
        desc_f  = T.font(10)
        head_f  = T.font(8, "bold")
        bf, df  = tkfont.Font(font=badge_f), tkfont.Font(font=desc_f)
        row_h   = T.px(30)
        badge_h = T.px(22)
        cpad    = T.px(14)

        # column sizes
        cols = []
        for title, rows in BINDINGS:
            bw = max(bf.measure(b) for b, _ in rows) + T.px(18)
            dw = max(df.measure(d) for _, d in rows)
            cols.append((title, rows, bw, cpad * 2 + bw + T.px(10) + dw))
        title_h = T.px(56)
        card_h  = cpad * 2 + T.px(22) + max(len(r) for _, r, _, _ in cols) * row_h
        width   = pad * 2 + sum(c[3] for c in cols) + gap * (len(cols) - 1)
        height  = title_h + card_h + pad
        cv.configure(width=width, height=height)
        self._bg = T.rrect(width, height, T.px(16), T.BG, T.BORDER, 1)
        cv.create_image(0, 0, anchor="nw", image=self._bg)

        # title bar
        cv.create_text(pad, T.px(30), anchor="w", text="🎮  Controller bindings",
                       fill=T.TEXT, font=T.font(13, "semibold"))
        close = cv.create_text(width - pad, T.px(30), anchor="e",
                               text="RS click or click here to close  ✕",
                               fill=T.DIM, font=T.font(9))
        cv.tag_bind(close, "<ButtonPress-1>", lambda e: self.hide())
        cv.tag_bind(close, "<Enter>", lambda e: cv.itemconfig(close, fill=T.ACCENT))
        cv.tag_bind(close, "<Leave>", lambda e: cv.itemconfig(close, fill=T.DIM))

        # cards
        x = pad
        for title, rows, bw, cw in cols:
            cv.create_image(x, title_h, anchor="nw",
                            image=T.rrect(cw, card_h, T.px(12), T.SURFACE))
            cv.create_text(x + cpad, title_h + cpad + T.px(6), anchor="w",
                           text=title, fill=T.HEADER, font=head_f)
            y = title_h + cpad + T.px(22) + row_h / 2
            for badge, desc in rows:
                cv.create_image(x + cpad, y, anchor="w",
                                image=T.rrect(bw, badge_h, T.px(6), T.SURFACE_HI))
                cv.create_text(x + cpad + bw / 2, y, text=badge,
                               fill=T.ACCENT, font=badge_f)
                cv.create_text(x + cpad + bw + T.px(10), y, anchor="w",
                               text=desc, fill=T.TEXT, font=desc_f)
                y += row_h
            x += cw + gap
