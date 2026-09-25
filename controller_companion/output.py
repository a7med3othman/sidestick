"""Real keyboard/mouse output via pynput (the Output used by Mapper)."""

from pynput.keyboard import Controller as KbCtrl, Key, KeyCode
from pynput.mouse import Button, Controller as MouseCtrl

from . import win32


class PynputOutput:
    def __init__(self):
        self.kb    = KbCtrl()
        self.mouse = MouseCtrl()

    def key_down(self, name): self.kb.press(getattr(Key, name))
    def key_up(self, name):   self.kb.release(getattr(Key, name))

    def tap(self, name):
        key = getattr(Key, name)
        try:     self.kb.press(key)
        finally: self.kb.release(key)

    def type_char(self, ch, altgr=False):
        if altgr:
            # AltGr combos depend on the keyboard layout, so send real keys
            self.kb.press(Key.alt_gr)
            try:
                self.kb.press(KeyCode.from_char(ch))
                self.kb.release(KeyCode.from_char(ch))
            finally:
                self.kb.release(Key.alt_gr)
        elif not win32.send_unicode(ch):
            self.kb.type(ch)

    def mouse_down(self, button): self.mouse.press(getattr(Button, button))
    def mouse_up(self, button):   self.mouse.release(getattr(Button, button))
    def click(self, button, count): self.mouse.click(getattr(Button, button), count)
    def move(self, dx, dy):       self.mouse.move(dx, dy)
    def scroll(self, dx, dy):     self.mouse.scroll(dx, dy)

    def caps_lock(self):
        return win32.caps_lock_on()
