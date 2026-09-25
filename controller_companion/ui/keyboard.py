"""On-screen keyboard view: 3D keycaps on a floating, non-activating deck.

The engine owns the keyboard state and sends snapshots; this only draws them
and reports mouse clicks back via `on_key(row, col)`.
"""

import tkinter as tk
import tkinter.font as tkfont

from ..layout import ROWS, key_text
from . import theme as T
from .widgets import FloatingWindow

# keycap colours: (top face, side)
CAP_CHAR     = ("#2b261c", "#161209")
CAP_ACTION   = ("#221e15", "#110e07")
CAP_HOVER    = ("#3a3326", "#1b160d")
CAP_SELECTED = (T.ACCENT,  "#9a3412")

HINTS = ("A press   ·   Y space   ·   X ⌫   ·   B del   ·   Start ⏎   ·   "
         "LT shift   ·   RT AltGr   ·   Back caps   ·   LB / RB size   ·   LS close")


class KeyboardView(FloatingWindow):

    def __init__(self, root, on_key):
        super().__init__(root, "Virtual Keyboard")
        self.on_key = on_key
        self.snap = {"visible": False, "row": 1, "col": 1, "shift": False,
                     "latched": False, "caps": False, "altgr": False, "scale": 1.0}
        self._hover   = None
        self._pressed = set()
        self._items   = {}
        self.cv = tk.Canvas(self.win, bg=T.BG, highlightthickness=0, bd=0)
        self.cv.pack()
        self._build()
        self.realize()

    # ── drawing ────────────────────────────────────────────────────────────

    def _build(self):
        cv, s = self.cv, self.snap["scale"]
        cv.delete("all")
        self._items.clear()

        self._u     = u     = T.px(46 * s)          # key height
        self._gap   = gap   = max(2, T.px(6 * s))
        self._depth = depth = max(2, T.px(4 * s))
        self._r     = T.px(7 * s)
        pitch = u + gap
        pad   = T.px(16)
        head  = T.px(40)

        width  = pad * 2 + int(15 * pitch - gap)
        keys_h = len(ROWS) * pitch - gap
        self._char_font   = T.font(max(8, round(13 * s)), "semibold")
        self._action_font = T.font(max(7, round(9.5 * s)), "semibold")
        hint_font = T.font(9)
        hint_h = tkfont.Font(font=hint_font).metrics("linespace") * (2 if s < 0.9 else 1)
        height = head + keys_h + T.px(14) + hint_h + pad

        cv.configure(width=width, height=height)
        cv.create_image(0, 0, anchor="nw",
                        image=T.rrect(width, height, T.px(14), T.SURFACE, T.BORDER, 1))

        # header: title + modifier chips
        cv.create_text(pad, head / 2 + T.px(2), anchor="w", text="⌨  Keyboard",
                       fill=T.TEXT, font=T.font(11, "semibold"))
        x = width - pad
        self._chips = {}
        for name in ("altgr", "caps", "shift"):
            label = {"altgr": "ALTGR", "caps": "CAPS", "shift": "SHIFT"}[name]
            f = T.font(8, "bold")
            w = tkfont.Font(font=f).measure(label) + T.px(18)
            h = T.px(20)
            img = cv.create_image(x - w, head / 2 + T.px(2), anchor="w")
            txt = cv.create_text(x - w / 2, head / 2 + T.px(2), text=label, font=f)
            self._chips[name] = (img, txt, w, h)
            x -= w + T.px(6)

        # keys
        y = head
        for r, row in enumerate(ROWS):
            x = pad
            for c, key in enumerate(row):
                kw = int(key.width * pitch - gap)
                tag = f"k{r}_{c}"
                img = cv.create_image(x, y, anchor="nw", tags=(tag,))
                txt = cv.create_text(x + kw / 2, y + (u - depth) / 2, tags=(tag,),
                                     font=self._char_font if key.is_char else self._action_font)
                led = None
                if key.action == "caps_lock":
                    d = max(4, T.px(6 * s))
                    led = cv.create_oval(x + kw - d * 2.2, y + d * 1.2,
                                         x + kw - d * 1.2, y + d * 2.2, width=0, tags=(tag,))
                self._items[(r, c)] = (img, txt, led, kw)
                cv.tag_bind(tag, "<Enter>",           lambda e, k=(r, c): self._set_hover(k))
                cv.tag_bind(tag, "<Leave>",           lambda e, k=(r, c): self._set_hover(None, k))
                cv.tag_bind(tag, "<ButtonPress-1>",   lambda e, k=(r, c): self._click(k))
                x += key.width * pitch
            y += pitch

        cv.create_text(width / 2, y - gap + T.px(14) + hint_h / 2, text=HINTS,
                       fill=T.DIM, font=hint_font, justify="center",
                       width=width - pad * 2)
        self._paint_all()

    def _paint_chips(self):
        for name, (img, txt, w, h) in self._chips.items():
            on = self.snap[name]
            self.cv.itemconfig(img, image=T.rrect(w, h, h // 2,
                                                  T.ACCENT if on else T.SURFACE_HI))
            self.cv.itemconfig(txt, fill=T.ON_ACCENT if on else T.DIM)

    def _paint_key(self, rc):
        r, c = rc
        key = ROWS[r][c]
        img, txt, led, kw = self._items[rc]
        snap = self.snap
        selected = (r, c) == (snap["row"], snap["col"])
        active = ((key.action == "shift" and snap["shift"]) or
                  (key.action == "caps_lock" and snap["caps"]))
        if selected:
            top, side = CAP_SELECTED
        elif rc == self._hover:
            top, side = CAP_HOVER
        else:
            top, side = CAP_CHAR if key.is_char else CAP_ACTION
        edge = T.ACCENT if (active and not selected) else None
        pressed = rc in self._pressed
        self.cv.itemconfig(img, image=T.keycap(kw, self._u, self._r, self._depth,
                                               top, side, pressed, edge))
        if key.is_char:
            label = key_text(key, snap["shift"], snap["caps"])
            color = T.TEXT
        else:
            label = key.label
            color = T.ACCENT if active else T.MUTED
        if selected:
            color = T.ON_ACCENT
        sink = (self._depth - max(1, self._depth // 3)) if pressed else 0
        x0, y0 = self.cv.coords(img)
        self.cv.coords(txt, x0 + kw / 2, y0 + (self._u - self._depth) / 2 + sink)
        self.cv.itemconfig(txt, text=label, fill=color)
        if led is not None:
            self.cv.itemconfig(led, fill=T.OK if snap["caps"] else "#3a3326")

    def _paint_all(self):
        self._paint_chips()
        for rc in self._items:
            self._paint_key(rc)

    # ── engine → view ──────────────────────────────────────────────────────

    def update_state(self, snap):
        old, self.snap = self.snap, dict(snap)
        if snap["scale"] != old["scale"]:
            self._build()
            if self.is_visible():
                self.place_bottom_center()
        elif (snap["shift"], snap["caps"], snap["altgr"], snap["latched"]) != \
                (old["shift"], old["caps"], old["altgr"], old["latched"]):
            self._paint_all()
        else:
            for rc in {(old["row"], old["col"]), (snap["row"], snap["col"])}:
                self._paint_key(rc)

        if snap["visible"] and not self.is_visible():
            self.place_bottom_center()
            self.show()
        elif not snap["visible"] and self.is_visible():
            self.hide()

    def flash(self, row, col):
        """Show a key as pressed for a moment."""
        rc = (row, col)
        if rc not in self._items:
            return
        self._pressed.add(rc)
        self._paint_key(rc)
        def release():
            self._pressed.discard(rc)
            if rc in self._items:
                self._paint_key(rc)
        self.win.after(110, release)

    # ── mouse ──────────────────────────────────────────────────────────────

    def _set_hover(self, rc, leaving=None):
        if rc is None and leaving != self._hover:
            return
        prev, self._hover = self._hover, rc
        for k in {prev, rc} - {None}:
            self._paint_key(k)

    def _click(self, rc):
        self.on_key(*rc)
