from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4


@dataclass
class Dot:
    id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    x: int = 0
    y: int = 0
    click_type: str = "click"  # click | double | hold | key
    key: Optional[str] = None
    delay_override_ms: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "click_type": self.click_type,
            "key": self.key,
            "delay_override_ms": self.delay_override_ms,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Dot":
        return Dot(
            id=str(data.get("id") or uuid4().hex),
            name=str(data.get("name") or ""),
            x=int(data.get("x") or 0),
            y=int(data.get("y") or 0),
            click_type=str(data.get("click_type") or "click"),
            key=data.get("key"),
            delay_override_ms=data.get("delay_override_ms"),
        )


@dataclass
class Settings:
    start_stop_hotkey: str = "f6"
    pause_resume_hotkey: str = "f7"
    pause_on_window_change: bool = True
    auto_resume_on_focus: bool = True
    window_check_interval_ms: int = 250

    loop_delay_ms: int = 500
    click_delay_ms: int = 250
    loop_count: int = 0  # 0 = infinite
    max_loops: int = 0  # 0 = no cap
    mouse_speed: int = 1
    click_speed_ms: int = 60
    randomize_order: bool = False
    random_delay_pct: int = 0
    minimize_on_start: bool = False
    restore_on_stop: bool = True

    default_infinite_loops: bool = True
    debug_mode: bool = False
    enable_logs: bool = True
    autosave_config: bool = True

    test_mode: bool = False

    overlay_opacity: float = 0.8
    theme: str = "dark"  # dark | light
    show_dot_numbers: bool = True
    show_coordinates: bool = False
    lock_dots: bool = False

    enable_roblox_mode: bool = True
    click_backend: str = "autoit"  # autoit | win32

    post_action: str = "none"  # none | beep | message | close

    tos_accepted_version: int = 0
    discord_prompt_shown: bool = False
    access_key_accepted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_stop_hotkey": self.start_stop_hotkey,
            "pause_resume_hotkey": self.pause_resume_hotkey,
            "pause_on_window_change": self.pause_on_window_change,
            "auto_resume_on_focus": self.auto_resume_on_focus,
            "window_check_interval_ms": self.window_check_interval_ms,
            "loop_delay_ms": self.loop_delay_ms,
            "click_delay_ms": self.click_delay_ms,
            "loop_count": self.loop_count,
            "max_loops": self.max_loops,
            "mouse_speed": self.mouse_speed,
            "click_speed_ms": self.click_speed_ms,
            "randomize_order": self.randomize_order,
            "random_delay_pct": self.random_delay_pct,
            "minimize_on_start": self.minimize_on_start,
            "restore_on_stop": self.restore_on_stop,
            "default_infinite_loops": self.default_infinite_loops,
            "debug_mode": self.debug_mode,
            "enable_logs": self.enable_logs,
            "autosave_config": self.autosave_config,
            "test_mode": self.test_mode,
            "overlay_opacity": self.overlay_opacity,
            "theme": self.theme,
            "show_dot_numbers": self.show_dot_numbers,
            "show_coordinates": self.show_coordinates,
            "lock_dots": self.lock_dots,
            "enable_roblox_mode": self.enable_roblox_mode,
            "click_backend": self.click_backend,
            "post_action": self.post_action,
            "tos_accepted_version": self.tos_accepted_version,
            "discord_prompt_shown": self.discord_prompt_shown,
            "access_key_accepted": self.access_key_accepted,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Settings":
        s = Settings()
        for k, v in (data or {}).items():
            if hasattr(s, k):
                setattr(s, k, v)
        return s


@dataclass
class AppState:
    settings: Settings = field(default_factory=Settings)
    dots: List[Dot] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "settings": self.settings.to_dict(),
            "dots": [d.to_dict() for d in self.dots],
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "AppState":
        settings = Settings.from_dict((data or {}).get("settings") or {})
        dots = [Dot.from_dict(x) for x in ((data or {}).get("dots") or [])]
        if not dots:
            dots = []
        return AppState(settings=settings, dots=dots)
