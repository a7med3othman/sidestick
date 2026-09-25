import pytest

from controller_companion import config as C
from controller_companion.config import Settings
from controller_companion.mapper import Mapper, PadState


class FakeOutput:
    def __init__(self):
        self.log = []
        self.keys = set()
        self.buttons = set()
        self.caps = False

    def key_down(self, k): self.log.append(("down", k)); self.keys.add(k)
    def key_up(self, k):   self.log.append(("up", k));   self.keys.discard(k)
    def tap(self, k):      self.log.append(("tap", k))
    def type_char(self, ch, altgr): self.log.append(("type", ch, altgr))
    def mouse_down(self, b): self.log.append(("mdown", b)); self.buttons.add(b)
    def mouse_up(self, b):   self.log.append(("mup", b));   self.buttons.discard(b)
    def click(self, b, n):   self.log.append(("click", b, n))
    def move(self, x, y):    self.log.append(("move", x, y))
    def scroll(self, x, y):  self.log.append(("scroll", x, y))
    def caps_lock(self):     return self.caps

    def taps(self, k): return self.log.count(("tap", k))


class Rig:
    """Drives a Mapper with a mutable fake controller and a fake clock."""

    def __init__(self):
        self.out = FakeOutput()
        self.m = Mapper(Settings(), self.out)
        self.buttons = [False] * C.NUM_BUTTONS
        self.axes = [0.0, 0.0, 0.0, 0.0, -1.0, -1.0]
        self.hat = (0, 0)
        self.now = 100.0
        self.m.connect(self.pad())

    def pad(self):
        return PadState(tuple(self.buttons), tuple(self.axes), self.hat)

    def step(self, n=1, dt=1 / 120):
        for _ in range(n):
            self.now += dt
            self.m.update(self.pad(), self.now, dt)

    def hold(self, btn, down=True):
        self.buttons[btn] = down
        self.step()

    def press(self, btn):
        self.hold(btn, True)
        self.hold(btn, False)

    def wait(self, seconds):
        self.step(dt=seconds)


@pytest.fixture
def rig():
    return Rig()


# ── Back: tap = Escape, hold = modifier ────────────────────────────────────

def test_back_tap_sends_escape(rig):
    rig.press(C.BTN_BACK)
    assert rig.out.taps("esc") == 1


def test_back_long_idle_hold_is_not_escape(rig):
    rig.hold(C.BTN_BACK)
    rig.wait(C.BACK_TAP_MAX + 0.1)
    rig.hold(C.BTN_BACK, False)
    assert rig.out.taps("esc") == 0


def test_alt_tab_holds_alt_until_back_released(rig):
    rig.hold(C.BTN_BACK)
    rig.press(C.BTN_LB)
    rig.press(C.BTN_LB)
    assert "alt" in rig.out.keys
    assert rig.out.taps("tab") == 2
    assert rig.out.log.count(("down", "alt")) == 1
    rig.hold(C.BTN_BACK, False)
    assert "alt" not in rig.out.keys
    assert rig.out.taps("esc") == 0


def test_alt_f4_during_alt_tab_keeps_alt(rig):
    rig.hold(C.BTN_BACK)
    rig.press(C.BTN_LB)
    rig.press(C.BTN_Y)
    assert "alt" in rig.out.keys and rig.out.taps("f4") == 1
    rig.hold(C.BTN_BACK, False)
    assert "alt" not in rig.out.keys


def test_back_chords(rig):
    rig.hold(C.BTN_BACK)
    rig.press(C.BTN_X)
    rig.press(C.BTN_A)
    rig.hat = (0, 1); rig.step(); rig.hat = (0, 0); rig.step()
    rig.hold(C.BTN_BACK, False)
    assert rig.out.taps("f5") == 1
    assert ("click", "left", 2) in rig.out.log
    assert rig.out.taps("media_volume_up") == 1
    assert rig.out.taps("esc") == 0


# ── modifiers never stick ──────────────────────────────────────────────────

def test_shift_released_when_keyboard_opens(rig):
    rig.axes[C.AXIS_LT] = 1.0; rig.step()
    assert "shift" in rig.out.keys
    rig.press(C.BTN_LS)
    assert rig.m.vk_visible
    assert "shift" not in rig.out.keys
    assert rig.m.vk_snapshot()["shift"]
    rig.axes[C.AXIS_LT] = -1.0; rig.step()
    assert not rig.m.vk_snapshot()["shift"]


def test_shift_follows_trigger_while_back_held(rig):
    rig.axes[C.AXIS_LT] = 1.0; rig.step()
    rig.hold(C.BTN_BACK)
    rig.axes[C.AXIS_LT] = -1.0; rig.step()
    assert "shift" not in rig.out.keys


def test_mouse_button_released_while_back_held(rig):
    rig.hold(C.BTN_A)
    assert "left" in rig.out.buttons
    rig.hold(C.BTN_BACK)
    rig.hold(C.BTN_A, False)
    assert "left" not in rig.out.buttons


def test_disconnect_releases_everything(rig):
    rig.axes[C.AXIS_RT] = 1.0
    rig.hold(C.BTN_X)
    assert "ctrl" in rig.out.keys and "right" in rig.out.buttons
    rig.m.disconnect()
    assert not rig.out.keys and not rig.out.buttons


def test_unarmed_trigger_at_zero_is_ignored():
    r = Rig()
    r.axes[C.AXIS_LT] = 0.0
    r.m.connect(r.pad())
    r.step(3)
    assert "shift" not in r.out.keys
    r.axes[C.AXIS_LT] = -1.0; r.step()
    r.axes[C.AXIS_LT] = 1.0;  r.step()
    assert "shift" in r.out.keys


# ── pause ──────────────────────────────────────────────────────────────────

def test_pause_combo_toggles_and_blocks_input(rig):
    rig.hold(C.BTN_BACK)
    rig.hold(C.BTN_START)
    rig.wait(C.PAUSE_HOLD + 0.05)
    assert rig.m.paused
    assert ("paused", True) in rig.m.events and ("rumble",) in rig.m.events
    rig.buttons[C.BTN_BACK] = rig.buttons[C.BTN_START] = False; rig.step()
    assert rig.out.taps("esc") == 0 and rig.out.taps("enter") == 0

    rig.out.log.clear()
    rig.press(C.BTN_A)
    rig.press(C.BTN_BACK)
    rig.axes[C.AXIS_LX] = 1.0; rig.step(10); rig.axes[C.AXIS_LX] = 0.0
    assert rig.out.log == []

    rig.hold(C.BTN_BACK)
    rig.hold(C.BTN_START)
    rig.wait(C.PAUSE_HOLD + 0.05)
    assert not rig.m.paused
    rig.buttons[C.BTN_BACK] = rig.buttons[C.BTN_START] = False; rig.step()
    assert rig.out.taps("esc") == 0


def test_pause_releases_held_inputs(rig):
    rig.hold(C.BTN_A)
    rig.axes[C.AXIS_LT] = 1.0; rig.step()
    rig.m.set_paused(True)
    assert not rig.out.keys and not rig.out.buttons


# ── pointer + scroll ───────────────────────────────────────────────────────

def moved(rig):
    return sum(e[1] for e in rig.out.log if e[0] == "move"), \
           sum(e[2] for e in rig.out.log if e[0] == "move")


def test_slow_deflection_still_moves(rig):
    rig.axes[C.AXIS_LX] = 0.25
    rig.step(120)
    assert moved(rig)[0] > 0


def test_speed_is_frame_rate_independent():
    a, b = Rig(), Rig()
    a.axes[C.AXIS_LX] = b.axes[C.AXIS_LX] = 0.8
    a.step(120, dt=1 / 120)
    b.step(60, dt=1 / 60)
    assert abs(moved(a)[0] - moved(b)[0]) <= 2


def test_precision_mode_slows_cursor():
    fast, slow = Rig(), Rig()
    fast.axes[C.AXIS_LX] = slow.axes[C.AXIS_LX] = 1.0
    slow.buttons[C.BTN_B] = True
    fast.step(60); slow.step(60)
    assert moved(slow)[0] == pytest.approx(moved(fast)[0] * Settings().precision, abs=2)


def test_scroll_vertical_and_horizontal(rig):
    rig.axes[C.AXIS_RY] = -1.0; rig.step(60)
    ups = [e for e in rig.out.log if e[0] == "scroll"]
    assert ups and all(e == ("scroll", 0, e[2]) and e[2] > 0 for e in ups)
    rig.out.log.clear()
    rig.axes[C.AXIS_RY] = 0.0; rig.axes[C.AXIS_RX] = 1.0; rig.step(60)
    rights = [e for e in rig.out.log if e[0] == "scroll"]
    assert rights and all(e[1] > 0 and e[2] == 0 for e in rights)


def test_scroll_accumulator_resets(rig):
    rig.m._scroll_accum[1] = 0.9
    rig.axes[C.AXIS_RY] = 0.5; rig.step()
    assert rig.m._scroll_accum[1] <= 0            # direction reversed
    rig.axes[C.AXIS_RY] = 0.0; rig.step()
    assert rig.m._scroll_accum == [0.0, 0.0]      # at rest
    rig.axes[C.AXIS_RY] = -0.5; rig.step()
    rig.hold(C.BTN_BACK)
    assert rig.m._scroll_accum == [0.0, 0.0]      # mode change


# ── D-pad ──────────────────────────────────────────────────────────────────

def test_dpad_diagonal_roll(rig):
    rig.hat = (0, 1); rig.step()
    rig.hat = (1, 1); rig.step()
    rig.hat = (0, 0); rig.step()
    assert rig.out.taps("up") == 1 and rig.out.taps("right") == 1


def test_dpad_auto_repeat(rig):
    rig.hat = (0, -1)
    rig.step()
    rig.wait(C.REPEAT_DELAY + 0.001)
    for _ in range(3):
        rig.wait(C.REPEAT_RATE + 0.001)
    assert rig.out.taps("down") == 5


def test_mute_does_not_repeat(rig):
    rig.hold(C.BTN_BACK)
    rig.hat = (-1, 0); rig.step()
    rig.wait(1.0); rig.wait(1.0)
    assert rig.out.taps("media_volume_mute") == 1


# ── on-screen keyboard ─────────────────────────────────────────────────────

def open_vk(rig):
    rig.press(C.BTN_LS)
    assert rig.m.vk_visible


def test_vk_types_selected_key(rig):
    open_vk(rig)
    rig.press(C.BTN_A)                       # starts on 'q'
    assert ("type", "q", False) in rig.out.log


def test_vk_back_is_caps_not_escape(rig):
    open_vk(rig)
    rig.press(C.BTN_BACK)
    assert rig.out.taps("caps_lock") == 1 and rig.out.taps("esc") == 0


def test_vk_shift_hold_and_caps(rig):
    open_vk(rig)
    rig.axes[C.AXIS_LT] = 1.0; rig.step()
    rig.press(C.BTN_A)
    rig.axes[C.AXIS_LT] = -1.0; rig.step()
    rig.out.caps = True; rig.step()
    rig.press(C.BTN_A)
    rig.axes[C.AXIS_LT] = 1.0; rig.step()
    rig.press(C.BTN_A)                       # caps + shift = lower case
    typed = [e[1] for e in rig.out.log if e[0] == "type"]
    assert typed == ["Q", "Q", "q"]


def test_vk_shift_latch_applies_once(rig):
    open_vk(rig)
    rig.m.vk_click(3, 0)                     # Shift keycap
    assert rig.m.vk_snapshot()["latched"]
    rig.m.vk_click(1, 1)                     # q
    rig.m.vk_click(1, 1)
    typed = [e[1] for e in rig.out.log if e[0] == "type"]
    assert typed == ["Q", "q"]


def test_vk_action_keys_and_hide(rig):
    open_vk(rig)
    rig.m.vk_click(0, 13)                    # backspace
    rig.m.vk_click(2, 12)                    # enter
    assert rig.out.taps("backspace") == 1 and rig.out.taps("enter") == 1
    rig.m.vk_click(4, 5)                     # hide
    assert not rig.m.vk_visible


def test_vk_altgr(rig):
    open_vk(rig)
    rig.axes[C.AXIS_RT] = 1.0; rig.step()
    assert "ctrl" not in rig.out.keys
    rig.press(C.BTN_A)
    assert ("type", "q", True) in rig.out.log


def test_vk_navigation_repeat(rig):
    open_vk(rig)
    rig.hat = (1, 0); rig.step()             # q → w
    rig.wait(C.REPEAT_DELAY + 0.001)         # → e
    rig.wait(C.REPEAT_RATE + 0.001)          # → r
    rig.hat = (0, 0); rig.step()
    assert rig.m.vk.selected.normal == "r"


def test_vk_resize_emits_scale(rig):
    open_vk(rig)
    rig.press(C.BTN_RB)
    assert rig.m.settings.vk_scale == pytest.approx(1.1)
    assert ("vk_scale", 1.1) in rig.m.events
    for _ in range(30):
        rig.press(C.BTN_LB)
    assert rig.m.settings.vk_scale == C.LIMITS["vk_scale"][0]


def test_overlay_event(rig):
    rig.press(C.BTN_RS)
    assert ("overlay",) in rig.m.events
