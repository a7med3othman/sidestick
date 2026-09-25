"""System-tray icon (pystray). Runs on its own thread; menu actions are
forwarded to the Tk thread through `post(("tray", command))`."""

import logging
import threading

from .. import config as C
from ..icon import make_icon

log = logging.getLogger(__name__)


class Tray:

    def __init__(self, post):
        self.post      = post
        self.paused    = False
        self.available = False
        self._icon     = None
        try:
            import pystray
        except Exception as e:                      # optional dependency
            log.warning("Tray icon unavailable: %s", e)
            return

        def cmd(name):
            return lambda icon, item: self.post(("tray", name))

        Item = pystray.MenuItem
        menu = pystray.Menu(
            Item("Show Controller Companion", cmd("show"), default=True),
            Item(lambda item: "Resume" if self.paused else "Pause", cmd("pause")),
            pystray.Menu.SEPARATOR,
            Item("Bindings overlay",   cmd("overlay")),
            Item("On-screen keyboard", cmd("keyboard")),
            Item("Settings…",          cmd("settings")),
            pystray.Menu.SEPARATOR,
            Item("Quit", cmd("quit")),
        )
        self._images = {p: make_icon(64, paused=p) for p in (False, True)}
        self._icon = pystray.Icon(C.APP_ID, self._images[False], C.APP_NAME, menu)
        self.available = True

    def start(self):
        if self._icon:
            threading.Thread(target=self._run, name="tray", daemon=True).start()

    def _run(self):
        try:
            self._icon.run()
        except Exception:
            log.exception("Tray icon failed")

    def set_paused(self, paused):
        self.paused = paused
        if self._icon:
            try:
                self._icon.icon  = self._images[paused]
                self._icon.title = f"{C.APP_NAME} ({'paused' if paused else 'running'})"
                self._icon.update_menu()
            except Exception:
                pass

    def notify(self, message):
        if self._icon:
            try: self._icon.notify(message, C.APP_NAME)
            except Exception: pass

    def stop(self):
        if self._icon:
            try: self._icon.stop()
            except Exception: pass
