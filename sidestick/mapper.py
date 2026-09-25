"""Controller → keyboard/mouse mapping logic.

Pure logic: it reads a PadState snapshot each tick and drives an Output.
No pygame, pynput or Tk in here, so every behaviour is unit-testable.

Output interface (see output.py for the real one):
    key_down(name) / key_up(name) / tap(name)   pynput Key attribute names
    type_char(ch, altgr)
    mouse_down(btn) / mouse_up(btn) / click(btn, n)   btn = "left" | "right"
    move(dx, dy) / scroll(dx, dy)
    caps_lock() -> bool
"""

from dataclasses import dataclass

from . import config as C
from .layout import KeyboardModel, key_text

REST_AXES = (0.0, 0.0, 0.0, 0.0, -1.0, -1.0)
HAT_DIRS  = ("up", "down", "left", "right")


@dataclass(frozen=True)
class PadState:
    buttons: tuple = (False,) * C.NUM_BUTTONS
    axes:    tuple = REST_AXES
    hat:     tuple = (0, 0)

    def btn(self, i):
        return i < len(self.buttons) and bool(self.buttons[i])

    def axis(self, i):
        return self.axes[i] if i < len(self.axes) else 0.0


def _hat_held(hat):
    hx, hy = hat
    return {"up": hy == 1, "down": hy == -1, "left": hx == -1, "right": hx == 1}


class Mapper:
    def __init__(self, settings, out):
        self.settings = settings
        self.out      = out
        self.paused   = False

        # on-screen keyboard state
        self.vk             = KeyboardModel()
        self.vk_visible     = False
        self.vk_shift_hold  = False   # LT held
        self.vk_shift_latch = False   # Shift keycap: applies to the next key
        self.vk_altgr       = False   # RT held
        self.caps           = False
        self.vk_dirty       = True    # snapshot needs re-sending to the UI

        # UI/device events for the host to consume:
        #   ("overlay",) ("paused", bool) ("rumble",) ("vk_scale", v) ("vk_key", r, c)
        self.events = []

        # Everything we press is tracked here so it can always be released
        # (disconnect, pause, crash, quit): nothing is left stuck down.
        self._held_keys  = set()
        self._held_mouse = set()

        # Triggers can report 0.0 (= "half pressed") until first moved, so each
        # trigger stays ignored until it has been seen at rest or has moved.
        self._trig_armed   = {C.AXIS_LT: True, C.AXIS_RT: True}
        self._trig_initial = {C.AXIS_LT: -1.0, C.AXIS_RT: -1.0}

        self.prev = PadState()
        self._pad = self.prev
        self._reset_transient()

    def _reset_transient(self):
        self._alt_tab_active = False
        self._back_down_at   = float("-inf")
        self._back_chorded   = False   # Back used as a modifier this hold
        self._combo_since    = None    # Back+Start pause combo
        self._combo_fired    = False
        self._move_accum     = [0.0, 0.0]
        self._scroll_accum   = [0.0, 0.0]
        self._hat_next       = {}      # direction → next auto-repeat time
        self._vk_dir         = (0, 0)
        self._vk_next        = 0.0

    # ── lifecycle ──────────────────────────────────────────────────────────

    def connect(self, pad):
        """A controller was (re)connected; `pad` is its current state."""
        self.release_all()
        self._reset_transient()
        for ax in (C.AXIS_LT, C.AXIS_RT):
            self._trig_armed[ax]   = False
            self._trig_initial[ax] = pad.axis(ax)
        self.prev = pad

    def disconnect(self):
        self.release_all()
        self._reset_transient()
        self.prev = PadState()

    def release_all(self):
        """Let go of every key and mouse button we are holding."""
        for name in list(self._held_keys):
            try: self.out.key_up(name)
            except Exception: pass
        for button in list(self._held_mouse):
            try: self.out.mouse_up(button)
            except Exception: pass
        self._held_keys.clear()
        self._held_mouse.clear()
        self._alt_tab_active = False
        self._move_accum     = [0.0, 0.0]
        self._scroll_accum   = [0.0, 0.0]
        if self.vk_shift_hold or self.vk_altgr:
            self.vk_shift_hold = self.vk_altgr = False
            self.vk_dirty = True

    def set_paused(self, paused):
        if paused == self.paused:
            return
        self.paused = paused
        if paused:
            self.release_all()
            self.hide_vk()
        self.events.append(("paused", paused))
        self.events.append(("rumble",))

    # ── on-screen keyboard control (also called from the UI) ───────────────

    def show_vk(self):
        if not self.vk_visible:
            self.vk_visible = True
            self._vk_dir    = (0, 0)
            self.vk_dirty   = True

    def hide_vk(self):
        if self.vk_visible:
            self.vk_visible     = False
            self.vk_shift_latch = False
            self.vk_dirty       = True

    def toggle_vk(self):
        self.hide_vk() if self.vk_visible else self.show_vk()

    def vk_click(self, row, col):
        """A key was clicked with the mouse."""
        if self.vk.select(row, col):
            self.vk_dirty = True
            self._vk_activate()

    def vk_snapshot(self):
        return {
            "visible": self.vk_visible,
            "row":     self.vk.row,
            "col":     self.vk.col,
            "shift":   self.vk_shift_hold or self.vk_shift_latch,
            "latched": self.vk_shift_latch,
            "caps":    self.caps,
            "altgr":   self.vk_altgr,
            "scale":   self.settings.vk_scale,
        }

    # ── input helpers ──────────────────────────────────────────────────────

    def _pressed(self, i):  return self._pad.btn(i) and not self.prev.btn(i)
    def _released(self, i): return not self._pad.btn(i) and self.prev.btn(i)

    def _stick(self, ax):
        """Deadzone-corrected stick axis, -1.0 .. +1.0 (up/left negative)."""
        v  = self._pad.axis(ax)
        dz = self.settings.deadzone
        if abs(v) < dz:
            return 0.0
        s = 1.0 if v > 0 else -1.0
        return s * min(1.0, (abs(v) - dz) / (1.0 - dz))

    def _trigger(self, ax):
        """Trigger pull 0.0 .. 1.0 (raw axis rests at -1.0)."""
        raw = self._pad.axis(ax)
        if not self._trig_armed[ax]:
            if raw < -0.5 or abs(raw - self._trig_initial[ax]) > 0.05:
                self._trig_armed[ax] = True
            else:
                return 0.0
        return (raw + 1.0) / 2.0

    def _hat_fire(self, now, repeat=()):
        """D-pad directions to act on this tick: new presses, plus auto-repeat
        for directions listed in `repeat` that are held down."""
        held, was = _hat_held(self._pad.hat), _hat_held(self.prev.hat)
        fired = []
        for d in HAT_DIRS:
            if not held[d]:
                self._hat_next.pop(d, None)
            elif not was[d]:
                fired.append(d)
                self._hat_next[d] = now + C.REPEAT_DELAY
            elif d in repeat and now >= self._hat_next.get(d, float("inf")):
                fired.append(d)
                self._hat_next[d] = now + C.REPEAT_RATE
        return fired

    # ── output helpers ─────────────────────────────────────────────────────

    def _set_key(self, name, down):
        if down and name not in self._held_keys:
            self.out.key_down(name); self._held_keys.add(name)
        elif not down and name in self._held_keys:
            self._held_keys.discard(name); self.out.key_up(name)

    def _set_mouse(self, button, down):
        if down and button not in self._held_mouse:
            self.out.mouse_down(button); self._held_mouse.add(button)
        elif not down and button in self._held_mouse:
            self._held_mouse.discard(button); self.out.mouse_up(button)

    # ── main tick ──────────────────────────────────────────────────────────

    def update(self, pad, now, dt):
        """Process one controller snapshot. `dt` = seconds since last tick."""
        self._pad = pad
        try:
            self._update(now, dt)
        finally:
            self.prev = pad

    def _update(self, now, dt):
        pad  = self._pad
        back = pad.btn(C.BTN_BACK)

        # Hold Back + Start → pause / resume (works while paused too).
        if back and pad.btn(C.BTN_START) and not self.vk_visible:
            if self._combo_since is None:
                self._combo_since = now
            elif not self._combo_fired and now - self._combo_since >= C.PAUSE_HOLD:
                self._combo_fired  = True
                self._back_chorded = True
                self.set_paused(not self.paused)
        else:
            self._combo_since = None
            self._combo_fired = False

        if self.paused:
            if self._pressed(C.BTN_BACK):
                self._back_chorded = True   # a Back press while paused is never Esc
            return

        lt_on   = self._trigger(C.AXIS_LT) > C.TRIGGER_THRESHOLD
        rt_on   = self._trigger(C.AXIS_RT) > C.TRIGGER_THRESHOLD
        vk_mode = self.vk_visible

        # Triggers: Shift/Ctrl normally, on-screen Shift/AltGr while the
        # keyboard is open. Evaluated every tick in every mode so a modifier
        # can't be left held across a mode change.
        self._set_key("shift", lt_on and not vk_mode)
        self._set_key("ctrl",  rt_on and not vk_mode)
        if (lt_on and vk_mode) != self.vk_shift_hold or (rt_on and vk_mode) != self.vk_altgr:
            self.vk_shift_hold = lt_on and vk_mode
            self.vk_altgr      = rt_on and vk_mode
            self.vk_dirty      = True

        if self._pressed(C.BTN_BACK):
            self._back_down_at = now
            self._back_chorded = vk_mode   # Back in the keyboard is Caps Lock

        if vk_mode:
            self._vk_tick(now)
        elif back:
            self._secondary_tick(now)
        else:
            self._primary_tick(now, dt)

        if vk_mode or back:
            self._move_accum   = [0.0, 0.0]
            self._scroll_accum = [0.0, 0.0]

        # Mouse buttons are released whenever their button is let go, whatever
        # mode we're in now (e.g. A held, then Back pressed, then A released).
        if "left" in self._held_mouse and not pad.btn(C.BTN_A):
            self._set_mouse("left", False)
        if "right" in self._held_mouse and not pad.btn(C.BTN_X):
            self._set_mouse("right", False)

        # Back released: drop Alt from Alt+Tab; a clean short tap = Escape.
        if self._released(C.BTN_BACK):
            if self._alt_tab_active:
                self._set_key("alt", False)
                self._alt_tab_active = False
            if (not self._back_chorded and not vk_mode
                    and now - self._back_down_at <= C.BACK_TAP_MAX):
                self.out.tap("esc")

    # ── primary layout ─────────────────────────────────────────────────────

    def _primary_tick(self, now, dt):
        s      = self.settings
        frames = dt * 60.0          # speeds are defined per 1/60 s

        # mouse movement with acceleration curve; B held = precision mode
        lx = self._stick(C.AXIS_LX)
        ly = self._stick(C.AXIS_LY)
        if lx or ly:
            mag   = min(1.0, (lx**2 + ly**2) ** 0.5)
            scale = mag ** s.accel_power / mag
            speed = s.mouse_speed * (s.precision if self._pad.btn(C.BTN_B) else 1.0)
            # keep the fractional pixels so slow, precise movement still moves
            fx = lx * scale * speed * frames + self._move_accum[0]
            fy = ly * scale * speed * frames + self._move_accum[1]
            mx, my = int(fx), int(fy)
            self._move_accum = [fx - mx, fy - my]
            if mx or my:
                self.out.move(mx, my)
        else:
            self._move_accum = [0.0, 0.0]

        # scroll: right stick, along whichever axis is pushed further
        rx = self._stick(C.AXIS_RX)
        ry = self._stick(C.AXIS_RY)
        axis = 0 if abs(rx) > abs(ry) else 1
        value = rx if axis == 0 else -ry           # stick up = scroll up
        self._scroll_accum[1 - axis] = 0.0
        if abs(value) < 0.01:
            self._scroll_accum[axis] = 0.0
        else:
            delta = value * s.scroll_speed * 0.15 * frames
            if self._scroll_accum[axis] * delta < 0:   # direction reversed
                self._scroll_accum[axis] = 0.0
            acc   = max(-10.0, min(10.0, self._scroll_accum[axis] + delta))
            steps = int(acc)
            if steps:
                self.out.scroll(steps if axis == 0 else 0, steps if axis == 1 else 0)
                acc -= steps
            self._scroll_accum[axis] = acc

        # buttons (mouse releases are handled in _update)
        if self._pressed(C.BTN_A): self._set_mouse("left",  True)
        if self._pressed(C.BTN_X): self._set_mouse("right", True)

        if self._pressed(C.BTN_Y):     self.out.tap("media_play_pause")
        if self._pressed(C.BTN_LB):    self.out.tap("media_previous")
        if self._pressed(C.BTN_RB):    self.out.tap("media_next")
        if self._pressed(C.BTN_START): self.out.tap("enter")

        # D-pad → arrow keys (auto-repeat while held)
        for d in self._hat_fire(now, repeat=HAT_DIRS):
            self.out.tap(d)

        if self._pressed(C.BTN_LS): self.show_vk()
        if self._pressed(C.BTN_RS): self.events.append(("overlay",))

    # ── secondary layout (Back held) ───────────────────────────────────────

    def _secondary_tick(self, now):
        volume = {"up": "media_volume_up", "down": "media_volume_down",
                  "left": "media_volume_mute"}
        for d in self._hat_fire(now, repeat=("up", "down")):
            if d in volume:
                self.out.tap(volume[d]); self._back_chorded = True

        if self._pressed(C.BTN_START):
            self._back_chorded = True       # part of the pause combo
        if self._pressed(C.BTN_X):
            self.out.tap("f5"); self._back_chorded = True
        if self._pressed(C.BTN_Y):
            self._back_chorded = True
            if self._alt_tab_active:        # Alt is already down
                self.out.tap("f4")
            else:
                self._set_key("alt", True)
                try:     self.out.tap("f4")
                finally: self._set_key("alt", False)
        if self._pressed(C.BTN_A):
            self._back_chorded = True
            self.out.click("left", 2)
        # Back + LB = Alt+Tab: Alt stays held while Back is held, each LB
        # press taps Tab to cycle windows
        if self._pressed(C.BTN_LB):
            self._back_chorded = True
            if not self._alt_tab_active:
                self._set_key("alt", True)
                self._alt_tab_active = True
            self.out.tap("tab")

    # ── on-screen keyboard layout ──────────────────────────────────────────

    def _vk_tick(self, now):
        caps = self.out.caps_lock()
        if caps != self.caps:
            self.caps, self.vk_dirty = caps, True

        # navigation: d-pad takes priority over stick
        hx, hy = self._pad.hat
        if hx or hy:
            dx, dy = hx, -hy   # hat up=+1 → row up=-1
        else:
            lx = self._stick(C.AXIS_LX)
            ly = self._stick(C.AXIS_LY)
            dx = (1 if lx > 0.5 else -1 if lx < -0.5 else 0)
            dy = (1 if ly > 0.5 else -1 if ly < -0.5 else 0)

        cur = (dx, dy)
        if cur == (0, 0):
            self._vk_dir = cur
        elif cur != self._vk_dir or now >= self._vk_next:
            self._vk_next = now + (C.REPEAT_DELAY if cur != self._vk_dir else C.REPEAT_RATE)
            self._vk_dir  = cur
            if self.vk.move(dx, dy):
                self.vk_dirty = True

        if self._pressed(C.BTN_A):     self._vk_activate()
        if self._pressed(C.BTN_Y):     self.out.tap("space")
        if self._pressed(C.BTN_X):     self.out.tap("backspace")
        if self._pressed(C.BTN_B):     self.out.tap("delete")
        if self._pressed(C.BTN_RS):    self.out.tap("tab")
        if self._pressed(C.BTN_START): self.out.tap("enter")
        if self._pressed(C.BTN_BACK):  self.out.tap("caps_lock")
        if self._pressed(C.BTN_LB):    self._vk_resize(-0.1)
        if self._pressed(C.BTN_RB):    self._vk_resize(+0.1)
        if self._pressed(C.BTN_LS):    self.hide_vk()

    def _vk_activate(self):
        key = self.vk.selected
        self.events.append(("vk_key", self.vk.row, self.vk.col))
        if key.is_char:
            shift = self.vk_shift_hold or self.vk_shift_latch
            self.out.type_char(key_text(key, shift, self.caps), self.vk_altgr)
            if self.vk_shift_latch:
                self.vk_shift_latch = False
                self.vk_dirty = True
        elif key.action == "shift":
            self.vk_shift_latch = not self.vk_shift_latch
            self.vk_dirty = True
        elif key.action == "hide":
            self.hide_vk()
        else:
            self.out.tap(key.action)

    def _vk_resize(self, delta):
        lo, hi = C.LIMITS["vk_scale"]
        v = round(max(lo, min(hi, self.settings.vk_scale + delta)), 2)
        if v != self.settings.vk_scale:
            self.settings.vk_scale = v
            self.events.append(("vk_scale", v))
            self.vk_dirty = True
