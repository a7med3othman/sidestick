"""Ember theme: colours, fonts, DPI scaling and anti-aliased shape images.

Tk's canvas can't anti-alias, so rounded shapes are rendered with Pillow
(supersampled) and cached as PhotoImages.
"""

import functools

from PIL import Image, ImageDraw, ImageTk

# ── palette ───────────────────────────────────────────────────────────────
BG          = "#111008"   # window background
SURFACE     = "#1c1910"   # cards
SURFACE_HI  = "#28231a"   # raised controls, keycaps
SURFACE_HOV = "#332c20"   # hovered controls
BORDER      = "#2e281d"
TRACK       = "#3a3226"   # slider track

ACCENT      = "#f97316"   # Ember orange
ACCENT_HI   = "#fb923c"
ACCENT_LO   = "#c2410c"
ACCENT_DEEP = "#7c2d12"
ON_ACCENT   = "#1c0d02"   # text on orange

TEXT        = "#fef3c7"   # warm cream
MUTED       = "#b5ab98"
DIM         = "#7a7164"
HEADER      = "#fbbf24"   # amber section headers
OK          = "#4ade80"
WARN        = "#fbbf24"
BAD         = "#f87171"

FONT      = "Segoe UI"
FONT_SEMI = "Segoe UI Semibold"

_scale = 1.0


def init(root):
    """Call once after creating the Tk root."""
    global _scale
    _scale = max(1.0, root.winfo_fpixels("1i") / 96.0)
    root.configure(bg=BG)
    root.option_add("*Font", (FONT, 10))


def px(v):
    """Design pixels (at 96 DPI) → screen pixels."""
    return int(round(v * _scale))


def font(size, weight="normal"):
    if weight == "semibold":
        return (FONT_SEMI, size)
    return (FONT, size, weight)


# ── anti-aliased shapes ───────────────────────────────────────────────────
_SS = 4   # supersampling factor


def _finish(img, w, h):
    return ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))


@functools.lru_cache(maxsize=2048)
def rrect(w, h, r, fill, outline=None, width=1):
    """Rounded rectangle image, w×h screen pixels."""
    w, h = max(1, int(w)), max(1, int(h))
    img = Image.new("RGBA", (w * _SS, h * _SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w * _SS - 1, h * _SS - 1], radius=r * _SS, fill=fill,
                        outline=outline, width=(width * _SS if outline else 0))
    return _finish(img, w, h)


@functools.lru_cache(maxsize=512)
def keycap(w, h, r, depth, top, side, pressed=False, edge=None):
    """A 3D keycap: a darker 'side' under a lighter top face.
    Pressed caps sink so only a sliver of side shows."""
    w, h = max(1, int(w)), max(1, int(h))
    S = _SS
    img = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    sink = depth - max(1, depth // 3) if pressed else 0
    d.rounded_rectangle([0, sink * S, w * S - 1, h * S - 1], radius=r * S, fill=side)
    d.rounded_rectangle([0, sink * S, w * S - 1, (h - depth + sink) * S - 1],
                        radius=r * S, fill=top,
                        outline=edge, width=(max(1, S * 3 // 2) if edge else 0))
    return _finish(img, w, h)


@functools.lru_cache(maxsize=256)
def circle(d, fill, ring=None, ring_w=0):
    d = max(1, int(d))
    img = Image.new("RGBA", (d * _SS, d * _SS), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    dr.ellipse([0, 0, d * _SS - 1, d * _SS - 1], fill=ring or fill)
    if ring:
        k = ring_w * _SS
        dr.ellipse([k, k, d * _SS - 1 - k, d * _SS - 1 - k], fill=fill)
    return _finish(img, d, d)
