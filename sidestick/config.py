"""Tunable constants, controller layout, and persisted user settings."""

import json
import logging
import os
from dataclasses import asdict, dataclass, fields, replace

log = logging.getLogger(__name__)

APP_NAME = "Sidestick"
APP_ID   = "Sidestick"

# ═══════════════════════════════════════════════════════════════════════════
#  TIMING / FEEL
# ═══════════════════════════════════════════════════════════════════════════

TICK_HZ            = 120    # input polling rate; movement is time-based so
                            # speeds don't depend on this
TRIGGER_THRESHOLD  = 0.25
REPEAT_DELAY       = 0.35   # first auto-repeat (D-pad arrows, keyboard nav)
REPEAT_RATE        = 0.06   # subsequent auto-repeats
BACK_TAP_MAX       = 0.5    # Back released within this many seconds (and unused
                            # as a modifier) counts as a tap → Escape
PAUSE_HOLD         = 1.0    # hold Back + Start this long to pause / resume
RECONNECT_INTERVAL = 1.5    # seconds between controller re-scans while disconnected

# ═══════════════════════════════════════════════════════════════════════════
#  CONTROLLER LAYOUT (Xbox Series X on Windows / SDL)
# ═══════════════════════════════════════════════════════════════════════════
#   ax0 = Left Stick X   (left=-1, right=+1)
#   ax1 = Left Stick Y   (up=-1,   down=+1)
#   ax2 = Right Stick X  (left=-1, right=+1)
#   ax3 = Right Stick Y  (up=-1,   down=+1)
#   ax4 = Left Trigger   (rest=-1, full=+1)
#   ax5 = Right Trigger  (rest=-1, full=+1)

AXIS_LX, AXIS_LY, AXIS_RX, AXIS_RY, AXIS_LT, AXIS_RT = range(6)

BTN_A, BTN_B, BTN_X, BTN_Y = 0, 1, 2, 3
BTN_LB, BTN_RB             = 4, 5
BTN_BACK, BTN_START        = 6, 7
BTN_LS, BTN_RS             = 8, 9
NUM_BUTTONS                = 16
HAT_IDX                    = 0

# ═══════════════════════════════════════════════════════════════════════════
#  USER SETTINGS
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Settings:
    mouse_speed:     float = 18.0   # px per 1/60 s at full tilt
    scroll_speed:    float = 5.0
    deadzone:        float = 0.15
    accel_power:     float = 2.0    # 1.0 = linear, 2.0 = smooth curve
    precision:       float = 0.35   # cursor speed multiplier while B is held
    vk_scale:        float = 1.0    # on-screen keyboard size
    start_minimized: bool  = False  # start hidden in the tray

    def clamped(self):
        vals = {}
        for name, (lo, hi) in LIMITS.items():
            vals[name] = max(lo, min(hi, float(getattr(self, name))))
        return replace(self, **vals)

    def copy(self):
        return replace(self)


LIMITS = {
    "mouse_speed":  (1.0, 60.0),
    "scroll_speed": (1.0, 20.0),
    "deadzone":     (0.0, 0.5),
    "accel_power":  (1.0, 4.0),
    "precision":    (0.1, 1.0),
    "vk_scale":     (0.6, 2.0),
}


def config_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_ID)


def settings_path():
    return os.path.join(config_dir(), "settings.json")


def load(path=None):
    """Read settings, falling back to defaults for anything missing or invalid."""
    path = path or settings_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return Settings()
    except (OSError, ValueError) as e:
        log.warning("Ignoring unreadable settings file %s: %s", path, e)
        return Settings()
    if not isinstance(data, dict):
        return Settings()

    s = Settings()
    for f in fields(Settings):
        if f.name not in data:
            continue
        v = data[f.name]
        if isinstance(f.default, bool):
            if isinstance(v, bool):
                setattr(s, f.name, v)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            setattr(s, f.name, float(v))
    return s.clamped()


def save(settings, path=None):
    path = path or settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(asdict(settings), f, indent=2)
    os.replace(tmp, path)
