"""App icon, drawn with Pillow so there are no binary assets to ship."""

from PIL import Image, ImageDraw

ORANGE = (249, 115, 22, 255)
GREY   = (87, 83, 78, 255)
INK    = (17, 16, 8, 255)


def make_icon(size=256, paused=False):
    S = 1024                                   # draw big, then downsample
    bg = GREY if paused else ORANGE
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.23), fill=bg)

    # gamepad silhouette: body + two grips
    d.rounded_rectangle([int(S * .15), int(S * .33), int(S * .85), int(S * .63)],
                        radius=int(S * .15), fill=INK)
    d.ellipse([int(S * .12), int(S * .40), int(S * .40), int(S * .78)], fill=INK)
    d.ellipse([int(S * .60), int(S * .40), int(S * .88), int(S * .78)], fill=INK)

    # d-pad
    cx, cy, arm, w = int(S * .31), int(S * .49), int(S * .085), int(S * .035)
    d.rectangle([cx - arm, cy - w, cx + arm, cy + w], fill=bg)
    d.rectangle([cx - w, cy - arm, cx + w, cy + arm], fill=bg)

    # face buttons
    r = int(S * .042)
    for bx, by in ((.69, .43), (.76, .50), (.62, .50), (.69, .57)):
        x, y = int(S * bx), int(S * by)
        d.ellipse([x - r, y - r, x + r, y + r], fill=bg)

    if paused:                                 # pause bars in the corner
        d.rounded_rectangle([int(S * .70), int(S * .06), int(S * .77), int(S * .27)],
                            radius=int(S * .02), fill=(254, 243, 199, 255))
        d.rounded_rectangle([int(S * .82), int(S * .06), int(S * .89), int(S * .27)],
                            radius=int(S * .02), fill=(254, 243, 199, 255))
    return img.resize((size, size), Image.LANCZOS)


def save_ico(path):
    make_icon(256).save(path, sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])


if __name__ == "__main__":
    import sys
    save_ico(sys.argv[1] if len(sys.argv) > 1 else "icon.ico")
