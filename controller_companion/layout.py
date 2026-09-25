"""On-screen keyboard layout and selection model (no UI, no I/O)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class VKey:
    normal:  str = ""        # character typed (char keys)
    shifted: str = ""        # character typed with Shift
    action:  str = ""        # action keys: backspace, tab, caps_lock, enter,
                             # shift, esc, delete, space, left, right, hide
    label:   str = ""        # label for action keys
    width:   float = 1.0     # in key units

    @property
    def is_char(self):
        return not self.action


def _chars(spec):
    """'`~ 1! 2@' → [VKey('`','~'), VKey('1','!'), ...]"""
    return [VKey(pair[0], pair[1]) for pair in spec.split(" ")]


def _act(action, label, width):
    return VKey(action=action, label=label, width=width)


# Every row is 15 units wide, like a real 60% keyboard.
ROWS = (
    tuple(_chars("`~ 1! 2@ 3# 4$ 5% 6^ 7& 8* 9( 0) -_ =+")
          + [_act("backspace", "⌫", 2.0)]),
    tuple([_act("tab", "Tab", 1.5)]
          + _chars("qQ wW eE rR tT yY uU iI oO pP [{ ]}")
          + [VKey("\\", "|", width=1.5)]),
    tuple([_act("caps_lock", "Caps", 1.75)]
          + _chars("aA sS dD fF gG hH jJ kK lL ;: '\"")
          + [_act("enter", "Enter", 2.25)]),
    tuple([_act("shift", "Shift", 2.25)]
          + _chars("zZ xX cC vV bB nN mM ,< .> /?")
          + [_act("shift", "Shift", 2.75)]),
    (_act("esc", "Esc", 1.5), _act("delete", "Del", 1.5),
     _act("space", "space", 7.0), _act("left", "←", 1.25),
     _act("right", "→", 1.25), _act("hide", "Hide", 2.5)),
)


def key_text(key, shift, caps):
    """The character a char key types (and displays) for this modifier state."""
    if key.normal.isalpha():
        return key.normal.upper() if shift != caps else key.normal
    return key.shifted if shift else key.normal


class KeyboardModel:
    """Tracks the selected key and moves it the way your eye expects on a
    staggered keyboard: up/down lands on the key physically above/below."""

    def __init__(self, rows=ROWS):
        self.rows = rows
        self.spans = []
        for row in rows:
            x, spans = 0.0, []
            for key in row:
                spans.append((x, x + key.width))
                x += key.width
            self.spans.append(spans)
        self.row, self.col = 1, 1          # start on 'q'

    @property
    def selected(self):
        return self.rows[self.row][self.col]

    def select(self, row, col):
        if 0 <= row < len(self.rows) and 0 <= col < len(self.rows[row]):
            self.row, self.col = row, col
            return True
        return False

    def move(self, dx, dy):
        """Move the selection; returns True if it changed."""
        r, c = self.row, self.col
        if dx:
            c = max(0, min(len(self.rows[r]) - 1, c + dx))
        if dy:
            nr = max(0, min(len(self.rows) - 1, r + dy))
            if nr != r:
                x0, x1 = self.spans[r][c]
                cx = (x0 + x1) / 2
                c = min(range(len(self.rows[nr])),
                        key=lambda i: _distance(self.spans[nr][i], cx))
                r = nr
        changed = (r, c) != (self.row, self.col)
        self.row, self.col = r, c
        return changed


def _distance(span, x):
    """Keys containing x win; otherwise the nearest key centre."""
    x0, x1 = span
    if x0 <= x < x1:
        return -1.0
    return abs(x - (x0 + x1) / 2)
