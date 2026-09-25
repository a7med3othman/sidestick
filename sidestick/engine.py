"""Input engine: owns the controller and runs the Mapper on its own thread.

Running off the Tk thread means input keeps flowing (and held buttons are
still released) even while a window is being dragged or redrawn.
The UI talks to it with send(); it reports back through `post(event)`.
"""

import logging
import os
import queue
import threading
import time

# Keep reading the controller while other apps have focus, and skip pygame's banner.
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
import pygame.locals as PGL

from . import config as C
from . import win32
from .mapper import Mapper, PadState

log = logging.getLogger(__name__)


class Engine(threading.Thread):

    def __init__(self, settings, post):
        super().__init__(name="input-engine", daemon=True)
        self.settings = settings
        self.post     = post
        self.cmds     = queue.Queue()
        self.js       = None
        self.mapper   = None
        self._next_connect_try = 0.0
        self._last_error_log   = 0.0

    # ── called from the UI thread ──────────────────────────────────────────

    def send(self, *cmd):
        self.cmds.put(cmd)

    def stop(self, timeout=2.0):
        self.send("quit")
        if self.is_alive():
            self.join(timeout)

    # ── thread body ────────────────────────────────────────────────────────

    def run(self):
        win32.timer_resolution(1, begin=True)
        try:
            self._run()
        except Exception:
            log.exception("Input engine crashed")
            self.post(("error", "Input engine stopped unexpectedly. See the log file."))
        finally:
            win32.timer_resolution(1, begin=False)

    def _run(self):
        from .output import PynputOutput
        pygame.display.init()      # needed for the event queue
        pygame.joystick.init()
        self.mapper = Mapper(self.settings, PynputOutput())
        self.post(("controller", None))
        period = 1.0 / C.TICK_HZ
        last   = time.perf_counter()
        try:
            while True:
                now = time.perf_counter()
                dt, last = min(now - last, 0.1), now
                if not self._handle_commands():
                    break
                self._step(now, dt)
                self._flush()
                time.sleep(max(0.0, period - (time.perf_counter() - now)))
        finally:
            # whatever happened (quit, crash), never leave keys held
            self.mapper.release_all()
            pygame.quit()

    def _handle_commands(self):
        m = self.mapper
        while True:
            try:
                cmd, *args = self.cmds.get_nowait()
            except queue.Empty:
                return True
            if cmd == "quit":
                return False
            elif cmd == "settings":
                m.settings = self.settings = args[0]
                m.vk_dirty = True
            elif cmd == "pause":
                m.set_paused(not m.paused if args[0] is None else args[0])
            elif cmd == "vk_toggle": m.toggle_vk()
            elif cmd == "vk_hide":   m.hide_vk()
            elif cmd == "vk_click":  m.vk_click(*args)

    def _step(self, now, dt):
        try:
            events = pygame.event.get()
        except pygame.error:
            events = []

        if self.js is None:
            if now >= self._next_connect_try or any(
                    ev.type == PGL.JOYDEVICEADDED for ev in events):
                self._try_connect(now)
            return

        for ev in events:
            if ev.type == PGL.JOYDEVICEREMOVED and self._is_our_device(ev):
                self._disconnect(now)
                return

        try:
            self.mapper.update(self._read_pad(), now, dt)
        except Exception:
            # keep running, but never with something held down
            self.mapper.release_all()
            if now - self._last_error_log > 5.0:
                self._last_error_log = now
                log.exception("Error while processing controller input")

    def _flush(self):
        m = self.mapper
        for ev in m.events:
            if ev[0] == "rumble":
                self._rumble()
            else:
                self.post(ev)
        m.events.clear()
        if m.vk_dirty:
            m.vk_dirty = False
            self.post(("vk", m.vk_snapshot()))

    # ── controller ─────────────────────────────────────────────────────────

    def _read_pad(self):
        js = self.js
        def safe(fn, i, default):
            try:    return fn(i)
            except Exception: return default
        return PadState(
            buttons=tuple(bool(safe(js.get_button, i, 0)) for i in range(C.NUM_BUTTONS)),
            axes=tuple(safe(js.get_axis, i, r) for i, r in enumerate((0.0, 0.0, 0.0, 0.0, -1.0, -1.0))),
            hat=safe(js.get_hat, C.HAT_IDX, (0, 0)),
        )

    def _is_our_device(self, ev):
        iid = getattr(ev, "instance_id", None)
        if iid is None:
            return True
        try:    return iid == self.js.get_instance_id()
        except Exception: return True

    def _try_connect(self, now):
        self._next_connect_try = now + C.RECONNECT_INTERVAL
        try:
            if pygame.joystick.get_count() == 0:
                # full re-scan as a fallback for drivers that miss hot-plug events
                pygame.joystick.quit()
                pygame.joystick.init()
            if pygame.joystick.get_count() == 0:
                return
            js = pygame.joystick.Joystick(0)
            js.init()
        except pygame.error as e:
            log.warning("Controller connect failed: %s", e)
            return
        self.js = js
        # pump so SDL reports stable values
        for _ in range(10):
            pygame.event.pump()
        name = js.get_name()
        log.info("Controller connected: %s (%d axes, %d buttons)",
                 name, js.get_numaxes(), js.get_numbuttons())
        self.mapper.connect(self._read_pad())
        self.post(("controller", name))

    def _disconnect(self, now):
        log.info("Controller disconnected")
        self.mapper.disconnect()
        self.js = None
        self._next_connect_try = now
        self.post(("controller", None))

    def _rumble(self):
        try:
            if self.js is not None:
                self.js.rumble(0.3, 0.7, 180)
        except Exception:
            pass
