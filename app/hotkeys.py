"""Global hotkeys from a low-level keyboard hook (pynput). Combos look like 'ctrl+win' or 'ctrl+alt+r'."""
import ctypes
import logging
import threading
import time

from pynput import keyboard

log = logging.getLogger("bark.hotkeys")
K = keyboard.Key
_MODS = {
    "ctrl": (K.ctrl, K.ctrl_l, K.ctrl_r),
    "win": (K.cmd, K.cmd_l, K.cmd_r),
    "alt": (K.alt, K.alt_l, K.alt_r, K.alt_gr),
    "shift": (K.shift, K.shift_l, K.shift_r),
}
_ALIASES = {"control": "ctrl", "cmd": "win", "super": "win", "windows": "win", "option": "alt", "esc": "escape",
            "return": "enter", "del": "delete"}
MASK_VK = 0xE8  # unassigned key, tapped while Win is held so the Start menu does not open on release


def token(key):
    for name, keys in _MODS.items():
        if key in keys:
            return name
    if isinstance(key, keyboard.Key):
        return key.name
    vk = getattr(key, "vk", None)
    if vk == MASK_VK:
        return None
    if vk is not None and (0x41 <= vk <= 0x5A or 0x30 <= vk <= 0x39):
        return chr(vk).lower()  # with Ctrl held, .char is a control code, so use the virtual key
    ch = getattr(key, "char", None)
    if ch:
        return ch.lower()
    return f"vk{vk}" if vk is not None else None


def parse_combo(text):
    parts = [p.strip().lower() for p in text.replace(" ", "").split("+") if p.strip()]
    return frozenset(_ALIASES.get(p, p) for p in parts)


class HotkeyManager:
    def __init__(self, post):
        """post(event_name, timestamp) is called from the hook thread; keep it cheap (e.g. queue.put).
        The timestamp is when the key actually moved, so a busy UI thread cannot distort hold times."""
        self.post = post
        self.bindings = {}  # name -> combo
        self.active = set()
        self.pressed = set()
        self.lock = threading.Lock()
        self.listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self.listener.daemon = True
        self.listener.start()

    def set_bindings(self, bindings):
        with self.lock:
            self.bindings = {name: parse_combo(c) for name, c in bindings.items() if c and c.strip()}
            self.active.clear()

    def wait_released(self, timeout=1.5):
        """Block until no keys are physically held, so synthetic Ctrl+V/Ctrl+C is not mixed with them."""
        end = time.time() + timeout
        while self.pressed and time.time() < end:
            time.sleep(0.02)
        time.sleep(0.05)

    def stop(self):
        self.listener.stop()

    def _on_press(self, key):
        t = token(key)
        if t is None:
            return
        with self.lock:
            self.pressed.add(t)
            if t == "escape":
                self.post("escape", time.time())
            for name, combo in self.bindings.items():
                if name not in self.active and combo == self.pressed:
                    self.active.add(name)
                    if "win" in combo:
                        u32 = ctypes.windll.user32
                        u32.keybd_event(MASK_VK, 0, 0, 0)
                        u32.keybd_event(MASK_VK, 0, 2, 0)
                    self.post(name + "_down", time.time())

    def _on_release(self, key):
        t = token(key)
        if t is None:
            return
        with self.lock:
            self.pressed.discard(t)
            for name in list(self.active):
                if not self.bindings.get(name, frozenset()) <= self.pressed:
                    self.active.discard(name)
                    self.post(name + "_up", time.time())
