from __future__ import annotations

import time
import re

from .models import Settings


class InputBackend:
    def move(self, x: int, y: int, speed: int) -> None:
        raise NotImplementedError

    def click(self, x: int, y: int) -> None:
        raise NotImplementedError

    def double_click(self, x: int, y: int, click_speed_ms: int) -> None:
        raise NotImplementedError

    def hold_click(self, x: int, y: int, hold_ms: int) -> None:
        raise NotImplementedError

    def key_press(self, key: str) -> None:
        raise NotImplementedError


class AutoItBackend(InputBackend):
    def __init__(self) -> None:
        import autoit  # type: ignore

        self._autoit = autoit

    def move(self, x: int, y: int, speed: int) -> None:
        self._autoit.mouse_move(x, y, speed=max(1, int(speed)))

    def click(self, x: int, y: int) -> None:
        self._autoit.mouse_click("left", x, y)

    def double_click(self, x: int, y: int, click_speed_ms: int) -> None:
        self._autoit.mouse_click("left", x, y, 2)
        if click_speed_ms > 0:
            time.sleep(click_speed_ms / 1000)

    def hold_click(self, x: int, y: int, hold_ms: int) -> None:
        self.move(x, y, speed=1)
        md = getattr(self._autoit, "mouse_down", None)
        mu = getattr(self._autoit, "mouse_up", None)
        if callable(md) and callable(mu):
            md("left")
            time.sleep(max(0, hold_ms) / 1000)
            mu("left")
            return

        self._autoit.mouse_click("left", x, y)
        time.sleep(max(0, hold_ms) / 1000)

    def key_press(self, key: str) -> None:
        if not key:
            return
        self._autoit.send(key)


class Win32Backend(InputBackend):
    def __init__(self) -> None:
        import ctypes

        self._ctypes = ctypes
        self._user32 = ctypes.windll.user32

        from pynput.keyboard import Controller  # type: ignore
        from pynput.keyboard import Key  # type: ignore

        self._kb = Controller()
        self._Key = Key

    def move(self, x: int, y: int, speed: int) -> None:
        self._user32.SetCursorPos(int(x), int(y))

    def _mouse_event(self, flags: int) -> None:
        self._user32.mouse_event(flags, 0, 0, 0, 0)

    def click(self, x: int, y: int) -> None:
        self.move(x, y, speed=1)
        self._mouse_event(0x0002)
        self._mouse_event(0x0004)

    def double_click(self, x: int, y: int, click_speed_ms: int) -> None:
        self.click(x, y)
        time.sleep(max(0, click_speed_ms) / 1000)
        self.click(x, y)

    def hold_click(self, x: int, y: int, hold_ms: int) -> None:
        self.move(x, y, speed=1)
        self._mouse_event(0x0002)
        time.sleep(max(0, hold_ms) / 1000)
        self._mouse_event(0x0004)

    def key_press(self, key: str) -> None:
        if not key:
            return

        for token in _tokenize_send_string(key):
            try:
                k = _map_token_to_key(token, self._Key)
                if k is not None:
                    self._kb.press(k)
                    self._kb.release(k)
                else:
                    if len(token) == 1:
                        self._kb.press(token)
                        self._kb.release(token)
                    else:
                        self._kb.type(token)
            except Exception:
                continue


_TOKEN_RE = re.compile(r"\{([^}]+)\}")


def _tokenize_send_string(s: str) -> list[str]:
    s = s or ""
    out: list[str] = []
    i = 0
    while i < len(s):
        if s[i] == "{":
            m = _TOKEN_RE.match(s, i)
            if m:
                out.append("{" + m.group(1) + "}")
                i = m.end()
                continue
        out.append(s[i])
        i += 1
    return out


def _map_token_to_key(token: str, Key) -> object | None:
    t = (token or "").strip()
    if not (t.startswith("{") and t.endswith("}")):
        return None

    name = t[1:-1].strip().lower()
    if not name:
        return None

    if len(name) == 1:
        return name

    mapping = {
        "space": Key.space,
        "enter": Key.enter,
        "return": Key.enter,
        "tab": Key.tab,
        "esc": Key.esc,
        "escape": Key.esc,
        "backspace": Key.backspace,
        "delete": Key.delete,
        "del": Key.delete,
        "up": Key.up,
        "down": Key.down,
        "left": Key.left,
        "right": Key.right,
        "shift": Key.shift,
        "ctrl": Key.ctrl,
        "control": Key.ctrl,
        "alt": Key.alt,
    }

    if name in mapping:
        return mapping[name]

    if name.startswith("f") and name[1:].isdigit():
        fn = getattr(Key, name, None)
        if fn is not None:
            return fn

    return None


def build_backend(settings: Settings) -> InputBackend:
    if settings.enable_roblox_mode and settings.click_backend == "autoit":
        try:
            return AutoItBackend()
        except Exception:
            return Win32Backend()
    return Win32Backend()
