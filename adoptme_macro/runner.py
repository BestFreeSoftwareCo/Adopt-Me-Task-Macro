from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from .input_backend import InputBackend
from .models import Dot, Settings


@dataclass
class RunnerStatus:
    state: str
    current_dot_index: int = 0
    current_loop: int = 0
    paused_reason: Optional[str] = None


class MacroRunner:
    def __init__(
        self,
        backend: InputBackend,
        get_settings: Callable[[], Settings],
        get_dots: Callable[[], List[Dot]],
        on_status: Callable[[RunnerStatus], None],
        on_flash_dot: Callable[[str], None],
        on_started: Callable[[bool], None],
        on_stopped: Callable[[], None],
    ) -> None:
        self._backend = backend
        self._get_settings = get_settings
        self._get_dots = get_dots
        self._on_status = on_status
        self._on_flash_dot = on_flash_dot
        self._on_started = on_started
        self._on_stopped = on_stopped

        self._logger = logging.getLogger("adoptme_macro")

        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._pause = threading.Event()

        self._status = RunnerStatus(state="STOPPED")

    def status(self) -> RunnerStatus:
        with self._lock:
            return RunnerStatus(**self._status.__dict__)

    def is_running(self) -> bool:
        return self.status().state == "RUNNING"

    def is_paused(self) -> bool:
        return self.status().state == "PAUSED"

    def start(self, preview: bool = False) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._pause.clear()
            self._status = RunnerStatus(state="RUNNING", current_dot_index=0, current_loop=0, paused_reason=None)

        self._thread = threading.Thread(target=self._run, args=(preview,), daemon=True)
        self._thread.start()
        self._on_started(preview)
        self._on_status(self.status())

    def stop(self, join: bool = True) -> None:
        with self._lock:
            was_active = self._status.state != "STOPPED"

        self._stop.set()
        self._pause.clear()

        t = self._thread
        if join and t is not None and t.is_alive() and t is not threading.current_thread():
            try:
                t.join(timeout=0.5)
            except Exception:
                pass

        alive = t is not None and t.is_alive()

        with self._lock:
            self._status = RunnerStatus(state="STOPPED", current_dot_index=0, current_loop=0, paused_reason=None)
            if not alive:
                self._thread = None
        self._on_status(self.status())
        if was_active:
            self._on_stopped()

    def pause(self, reason: str = "user") -> None:
        with self._lock:
            if self._status.state != "RUNNING":
                return
            self._status.state = "PAUSED"
            self._status.paused_reason = reason
        self._pause.set()
        self._on_status(self.status())

    def resume(self, reason: str = "user") -> None:
        with self._lock:
            if self._status.state != "PAUSED":
                return
            if self._status.paused_reason == "user" and reason == "focus":
                return
            self._status.state = "RUNNING"
            self._status.paused_reason = None
        self._pause.clear()
        self._on_status(self.status())

    def toggle_start_stop(self) -> None:
        st = self.status().state
        if st in ("RUNNING", "PAUSED"):
            self.stop()
        else:
            self.start(preview=False)

    def toggle_pause_resume(self) -> None:
        st = self.status().state
        if st == "RUNNING":
            self.pause(reason="user")
        elif st == "PAUSED":
            self.resume(reason="user")

    def _run(self, preview: bool) -> None:
        try:
            while not self._stop.is_set():
                settings = self._get_settings()
                dots = list(self._get_dots())
                if not dots:
                    self.stop(join=False)
                    return

                loop_target = int(settings.loop_count or 0)
                loop_cap = int(settings.max_loops or 0)

                if preview:
                    loop_target = 1
                    loop_cap = 1

                while not self._stop.is_set():
                    if self._pause.is_set():
                        if self._stop.wait(0.05):
                            return
                        continue

                    order = list(range(len(dots)))
                    if settings.randomize_order:
                        random.shuffle(order)

                    with self._lock:
                        loop_index = self._status.current_loop

                    if loop_cap and loop_index >= loop_cap:
                        self.stop(join=False)
                        return

                    if loop_target and loop_index >= loop_target:
                        self.stop(join=False)
                        return

                    for i in order:
                        if self._stop.is_set():
                            return
                        while self._pause.is_set() and not self._stop.is_set():
                            if self._stop.wait(0.05):
                                return

                        dot = dots[i]
                        with self._lock:
                            self._status.current_dot_index = i
                        self._on_status(self.status())

                        delay_ms = dot.delay_override_ms if dot.delay_override_ms is not None else settings.click_delay_ms
                        delay_ms = int(max(0, delay_ms))

                        if settings.random_delay_pct:
                            pct = max(0, int(settings.random_delay_pct))
                            delta = delay_ms * (random.uniform(-pct, pct) / 100.0)
                            delay_ms = int(max(0, delay_ms + delta))

                        if preview:
                            self._on_flash_dot(dot.id)
                        else:
                            self._execute_dot(dot, settings)

                        if self._wait_with_pause(delay_ms / 1000.0):
                            return

                    with self._lock:
                        self._status.current_loop += 1
                    self._on_status(self.status())

                    if self._wait_with_pause(max(0, int(settings.loop_delay_ms)) / 1000.0):
                        return
        except Exception:
            try:
                self._logger.exception("Runner crashed")
            except Exception:
                pass
            try:
                self.stop(join=False)
            except Exception:
                pass
        finally:
            return

    def _wait_with_pause(self, seconds: float) -> bool:
        remaining = float(max(0.0, seconds))
        while remaining > 0 and not self._stop.is_set():
            if self._pause.is_set():
                if self._stop.wait(0.05):
                    return True
                continue

            step = min(0.05, remaining)
            if self._stop.wait(step):
                return True
            remaining -= step

        return self._stop.is_set()

    def _execute_dot(self, dot: Dot, settings: Settings) -> None:
        self._backend.move(dot.x, dot.y, speed=int(settings.mouse_speed))
        if dot.click_type == "click":
            self._backend.click(dot.x, dot.y)
        elif dot.click_type == "double":
            self._backend.double_click(dot.x, dot.y, click_speed_ms=int(settings.click_speed_ms))
        elif dot.click_type == "hold":
            self._backend.hold_click(dot.x, dot.y, hold_ms=int(settings.click_speed_ms))
        elif dot.click_type == "key":
            if dot.key:
                self._backend.key_press(dot.key)
        else:
            self._backend.click(dot.x, dot.y)
