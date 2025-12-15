from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional

from pynput import keyboard  # type: ignore


def _normalize_hotkey(hk: str) -> str:
    s = (hk or "").strip().lower().replace(" ", "")
    if not s:
        raise ValueError("Hotkey is required")

    if s.startswith("<") and s.endswith(">"):
        return s

    if "+" in s:
        parts = [p for p in s.split("+") if p]
        out = []
        for p in parts:
            if p.startswith("<") and p.endswith(">"):
                out.append(p)
                continue
            if p in ("ctrl", "control"):
                out.append("<ctrl>")
            elif p in ("shift",):
                out.append("<shift>")
            elif p in ("alt",):
                out.append("<alt>")
            elif p.startswith("f") and p[1:].isdigit():
                out.append(f"<{p}>")
            elif len(p) == 1:
                out.append(p)
            else:
                out.append(f"<{p}>")
        return "+".join(out)

    if s.startswith("f") and s[1:].isdigit():
        return f"<{s}>"

    if len(s) == 1:
        return s

    return f"<{s}>"


@dataclass
class HotkeyConfig:
    start_stop: str
    pause_resume: str
    emergency_stop: str = "<ctrl>+<shift>+s"


class HotkeyManager:
    def __init__(
        self,
        config: HotkeyConfig,
        on_start_stop: Callable[[], None],
        on_pause_resume: Callable[[], None],
        on_emergency_stop: Callable[[], None],
    ) -> None:
        self._config = config
        self._on_start_stop = on_start_stop
        self._on_pause_resume = on_pause_resume
        self._on_emergency_stop = on_emergency_stop
        self._listener: Optional[keyboard.GlobalHotKeys] = None

    def start(self) -> None:
        mapping: Dict[str, Callable[[], None]] = {
            _normalize_hotkey(self._config.start_stop): self._on_start_stop,
            _normalize_hotkey(self._config.pause_resume): self._on_pause_resume,
            _normalize_hotkey(self._config.emergency_stop): self._on_emergency_stop,
        }
        new_listener = keyboard.GlobalHotKeys(mapping)
        self.stop()
        self._listener = new_listener
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def update(self, config: HotkeyConfig) -> None:
        self._config = config
        self.start()
