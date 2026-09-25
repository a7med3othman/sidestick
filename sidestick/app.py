"""Application entry point: wires the input engine, windows and tray together.

Threads:
    main    Tk UI (all windows)
    engine  pygame + Mapper + keyboard/mouse output
    tray    pystray message loop
Engine and tray talk to the UI through one queue, drained every 15 ms.
"""

import argparse
import logging
import logging.handlers
import os
import queue
import signal
import sys
import tkinter as tk

from . import __version__
from . import config as C
from . import win32

log = logging.getLogger("sidestick")


class App:

    def __init__(self, root, settings, instance, start_hidden):
        from .engine import Engine
        from .ui.keyboard import KeyboardView
        from .ui.main_window import MainWindow
        from .ui.overlay import Overlay
        from .ui.settings import SettingsWindow
        from .ui.tray import Tray

        self.root         = root
        self.settings     = settings
        self.instance     = instance
        self.start_hidden = start_hidden
        self.events       = queue.Queue()
        self.controller   = None
        self.paused       = False
        self.error        = None
        self._save_job    = None
        self._told_tray   = False
        self._quitting    = False

        self.engine = Engine(settings.copy(), self.events.put)
        self.tray   = Tray(self.events.put)
        self.main   = MainWindow(root,
                                 on_close=self.close_main,
                                 on_pause=lambda: self.engine.send("pause", None),
                                 on_overlay=self.toggle_overlay,
                                 on_keyboard=lambda: self.engine.send("vk_toggle"),
                                 on_settings=self.show_settings)
        self.overlay  = Overlay(root)
        self.keyboard = KeyboardView(root, on_key=lambda r, c: self.engine.send("vk_click", r, c))
        self.settings_win = SettingsWindow(root, settings,
                                           on_change=self._settings_changed,
                                           on_restart_admin=self.restart_as_admin)
        root.report_callback_exception = self._tk_error

    # ── lifecycle ──────────────────────────────────────────────────────────

    def run(self):
        self.engine.start()
        self.tray.start()
        if self.start_hidden and self.tray.available:
            self.main.hide()
        else:
            self.main.show()
        self.root.after(15, self._pump)
        try:
            self.root.mainloop()
        finally:
            self._shutdown()
        return 0

    def quit(self):
        if not self._quitting:
            self._quitting = True
            self.root.quit()

    def _shutdown(self):
        self.engine.stop()              # releases every held key/button
        self.tray.stop()
        self._flush_save()
        self.instance.release()
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        log.info("Stopped")

    def close_main(self):
        if not self.tray.available:
            self.quit()
            return
        self.main.hide()
        if not self._told_tray:
            self._told_tray = True
            self.tray.notify("Still running in the tray. Right-click the icon to quit.")

    def restart_as_admin(self):
        if win32.relaunch_as_admin(["--elevated-restart"]):
            self.quit()

    # ── events from engine / tray ──────────────────────────────────────────

    def _pump(self):
        try:
            while True:
                self._handle(self.events.get_nowait())
        except queue.Empty:
            pass
        if not self._quitting:
            self.root.after(15, self._pump)

    def _handle(self, ev):
        kind, *args = ev
        if kind == "controller":
            self.controller = args[0]
            self._update_status()
        elif kind == "paused":
            self.paused = args[0]
            self.tray.set_paused(self.paused)
            self._update_status()
        elif kind == "error":
            self.error = args[0]
            self._update_status()
            self.main.show()
        elif kind == "overlay":
            self.toggle_overlay()
        elif kind == "vk":
            self.keyboard.update_state(args[0])
        elif kind == "vk_key":
            self.keyboard.flash(*args)
        elif kind == "vk_scale":
            self.settings.vk_scale = args[0]
            self._schedule_save()
        elif kind == "tray":
            self._tray_command(args[0])

    def _tray_command(self, cmd):
        if cmd == "show":       self.main.show()
        elif cmd == "pause":    self.engine.send("pause", None)
        elif cmd == "overlay":  self.toggle_overlay()
        elif cmd == "keyboard": self.engine.send("vk_toggle")
        elif cmd == "settings": self.show_settings()
        elif cmd == "quit":     self.quit()

    def _update_status(self):
        self.main.set_state(self.controller, self.paused, self.error)

    def toggle_overlay(self):
        self.overlay.toggle()

    def show_settings(self):
        self.settings_win.show()

    # ── settings ───────────────────────────────────────────────────────────

    def _settings_changed(self):
        self.engine.send("settings", self.settings.copy())
        self._schedule_save()

    def _schedule_save(self):
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(400, self._flush_save)

    def _flush_save(self):
        if self._save_job:
            try: self.root.after_cancel(self._save_job)
            except tk.TclError: pass
            self._save_job = None
        try:
            C.save(self.settings)
        except OSError as e:
            log.warning("Couldn't save settings: %s", e)

    def _tk_error(self, exc, value, tb):
        log.error("UI error", exc_info=(exc, value, tb))


# ═══════════════════════════════════════════════════════════════════════════

def setup_logging():
    handlers = []
    try:
        os.makedirs(C.config_dir(), exist_ok=True)
        handlers.append(logging.handlers.RotatingFileHandler(
            os.path.join(C.config_dir(), "log.txt"), maxBytes=256_000,
            backupCount=1, encoding="utf-8"))
    except OSError:
        pass
    if sys.stderr is not None:                  # None under pythonw / the .exe
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="sidestick",
                                     description="Use an Xbox controller as a mouse and keyboard.")
    parser.add_argument("--minimized", action="store_true", help="start hidden in the tray")
    parser.add_argument("--elevated-restart", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)

    setup_logging()
    log.info("Sidestick %s starting (admin=%s)", __version__, win32.is_admin())
    win32.set_dpi_aware()
    win32.set_app_id(f"{C.APP_ID}.{__version__}")

    instance = win32.SingleInstance(C.APP_ID)
    if not instance.acquire(wait=5.0 if args.elevated_restart else 0.0):
        win32.message_box("Sidestick is already running.\n\n"
                          "Look for its icon in the system tray.", C.APP_NAME)
        return 1

    try:
        from .ui import theme
        root = tk.Tk()
        root.withdraw()
        theme.init(root)
        settings = C.load()
        app = App(root, settings, instance,
                  start_hidden=args.minimized or settings.start_minimized)
        if hasattr(signal, "SIGBREAK"):          # console closed / Ctrl+Break
            signal.signal(signal.SIGBREAK, lambda *_: app.quit())
        signal.signal(signal.SIGINT, lambda *_: app.quit())
        return app.run()
    except Exception:
        log.exception("Fatal error")
        win32.message_box("Sidestick hit an unexpected error and closed.\n\n"
                          f"Details are in:\n{os.path.join(C.config_dir(), 'log.txt')}",
                          C.APP_NAME)
        return 1
    finally:
        instance.release()
