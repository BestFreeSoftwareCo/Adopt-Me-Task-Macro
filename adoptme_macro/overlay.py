from __future__ import annotations

import tkinter as tk
import sys
import ctypes
from typing import Callable, Dict

from .models import Dot, Settings


_TRANSPARENT_COLOR = "#010203"


def _hex_to_colorref(color: str) -> int:
    c = (color or "").lstrip("#")
    if len(c) != 6:
        return 0
    r = int(c[0:2], 16)
    g = int(c[2:4], 16)
    b = int(c[4:6], 16)
    return (b << 16) | (g << 8) | r


def _apply_win32_colorkey_alpha(win: tk.Toplevel, alpha: float) -> bool:
    if sys.platform != "win32":
        return False
    try:
        win.update_idletasks()
        hwnd = win.winfo_id()
        user32 = ctypes.windll.user32

        LWA_COLORKEY = 0x00000001
        LWA_ALPHA = 0x00000002
        color_key = _hex_to_colorref(_TRANSPARENT_COLOR)
        a = int(max(0, min(255, round(float(alpha) * 255.0))))

        res = user32.SetLayeredWindowAttributes(hwnd, color_key, a, LWA_COLORKEY | LWA_ALPHA)
        return bool(res)
    except Exception:
        return False


class DotOverlay:
    def __init__(
        self,
        root: tk.Misc,
        dot: Dot,
        index: int,
        settings: Settings,
        on_moved: Callable[[Dot], None],
    ) -> None:
        self.dot = dot
        self.index = index
        self.settings = settings
        self._on_moved = on_moved

        self._win = tk.Toplevel(root)
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        if sys.platform != "win32":
            self._win.attributes("-alpha", float(settings.overlay_opacity))

        try:
            self._win.configure(bg=_TRANSPARENT_COLOR)
        except Exception:
            pass

        self._size = 44
        self._win.geometry(f"{self._size}x{self._size}+{max(0, dot.x - 22)}+{max(0, dot.y - 22)}")

        self._canvas = tk.Canvas(
            self._win,
            width=self._size,
            height=self._size,
            highlightthickness=0,
            bd=0,
            bg=_TRANSPARENT_COLOR,
        )
        self._canvas.pack(fill="both", expand=True)

        self._circle = self._canvas.create_oval(6, 6, self._size - 6, self._size - 6, fill="#4F8CFF", outline="")
        self._text = self._canvas.create_text(
            self._size // 2,
            self._size // 2,
            text="",
            fill="white",
            font=("Segoe UI", 10, "bold"),
        )

        self._render_label()

        self._drag_off_x = 0
        self._drag_off_y = 0

        self._locked = False
        self.set_locked(bool(settings.lock_dots))

        if sys.platform == "win32":
            ok = _apply_win32_colorkey_alpha(self._win, float(settings.overlay_opacity))
            if not ok:
                try:
                    self._win.attributes("-transparentcolor", _TRANSPARENT_COLOR)
                    self._win.attributes("-alpha", 1.0)
                except Exception:
                    pass

        self._flash_job = None

    def _on_down(self, event: tk.Event) -> None:
        self._drag_off_x = event.x
        self._drag_off_y = event.y

    def _on_drag(self, event: tk.Event) -> None:
        x = self._win.winfo_pointerx() - self._drag_off_x
        y = self._win.winfo_pointery() - self._drag_off_y
        self._win.geometry(f"{self._size}x{self._size}+{x}+{y}")

        cx = x + self._size // 2
        cy = y + self._size // 2
        self.dot.x = int(cx)
        self.dot.y = int(cy)
        self._render_label()
        self._on_moved(self.dot)

    def _render_label(self) -> None:
        parts: list[str] = []
        if self.settings.show_dot_numbers:
            parts.append(str(self.index + 1))
        if self.settings.show_coordinates:
            parts.append(f"{int(self.dot.x)},{int(self.dot.y)}")

        self._canvas.itemconfigure(self._text, text="\n".join(parts))
        if len(parts) > 1:
            self._canvas.itemconfigure(self._text, font=("Segoe UI", 8, "bold"))
        else:
            self._canvas.itemconfigure(self._text, font=("Segoe UI", 10, "bold"))

    def set_visible(self, visible: bool) -> None:
        if visible:
            self._win.deiconify()
        else:
            self._win.withdraw()

    def destroy(self) -> None:
        if getattr(self, "_flash_job", None) is not None:
            try:
                self._win.after_cancel(self._flash_job)
            except Exception:
                pass
            self._flash_job = None
        try:
            self._win.destroy()
        except Exception:
            pass

    def update_index(self, index: int) -> None:
        self.index = index
        self._render_label()

    def apply_settings(self, settings: Settings) -> None:
        self.settings = settings
        if sys.platform == "win32":
            ok = _apply_win32_colorkey_alpha(self._win, float(settings.overlay_opacity))
            if not ok:
                try:
                    self._win.attributes("-transparentcolor", _TRANSPARENT_COLOR)
                    self._win.attributes("-alpha", 1.0)
                except Exception:
                    pass
        else:
            try:
                self._win.attributes("-alpha", float(settings.overlay_opacity))
            except Exception:
                pass
        self.set_locked(bool(settings.lock_dots))
        self._render_label()

    def set_locked(self, locked: bool) -> None:
        self._locked = bool(locked)

        if self._locked:
            try:
                self._win.unbind("<ButtonPress-1>")
                self._win.unbind("<B1-Motion>")
            except Exception:
                pass
        else:
            self._win.bind("<ButtonPress-1>", self._on_down)
            self._win.bind("<B1-Motion>", self._on_drag)

        _set_click_through(self._win, self._locked)

    def flash(self, color: str = "#00FF7A", ms: int = 120) -> None:
        try:
            self._canvas.itemconfigure(self._circle, fill=color)
        except Exception:
            return

        if getattr(self, "_flash_job", None) is not None:
            try:
                self._win.after_cancel(self._flash_job)
            except Exception:
                pass
            self._flash_job = None

        def restore() -> None:
            try:
                self._canvas.itemconfigure(self._circle, fill="#4F8CFF")
            except Exception:
                return

        try:
            self._flash_job = self._win.after(ms, restore)
        except Exception:
            self._flash_job = None


class OverlayManager:
    def __init__(self, root: tk.Misc, settings: Settings, on_dot_moved: Callable[[Dot], None]) -> None:
        self._root = root
        self._settings = settings
        self._on_dot_moved = on_dot_moved
        self._overlays: Dict[str, DotOverlay] = {}
        self._visible = True

    def set_settings(self, settings: Settings) -> None:
        self._settings = settings
        for ov in self._overlays.values():
            ov.apply_settings(settings)

    def set_locked(self, locked: bool) -> None:
        for ov in self._overlays.values():
            ov.set_locked(locked)

    def set_visible(self, visible: bool) -> None:
        self._visible = visible
        for ov in self._overlays.values():
            ov.set_visible(visible)

    def is_visible(self) -> bool:
        return self._visible

    def add_dot(self, dot: Dot, index: int) -> None:
        ov = DotOverlay(self._root, dot, index=index, settings=self._settings, on_moved=self._on_dot_moved)
        self._overlays[dot.id] = ov
        ov.set_visible(self._visible)

    def remove_dot(self, dot_id: str) -> None:
        ov = self._overlays.pop(dot_id, None)
        if ov is not None:
            ov.destroy()

    def clear(self) -> None:
        for ov in list(self._overlays.values()):
            ov.destroy()
        self._overlays.clear()

    def rebuild(self, dots: list[Dot]) -> None:
        visible = self._visible
        self.clear()
        for idx, dot in enumerate(dots):
            self.add_dot(dot, index=idx)
        self.set_visible(visible)

    def reindex(self, dots: list[Dot]) -> None:
        for idx, dot in enumerate(dots):
            ov = self._overlays.get(dot.id)
            if ov is not None:
                ov.update_index(idx)

    def flash_dot(self, dot_id: str) -> None:
        ov = self._overlays.get(dot_id)
        if ov is not None:
            ov.flash()


def _set_click_through(win: tk.Toplevel, enabled: bool) -> None:
    if sys.platform != "win32":
        return
    try:
        hwnd = win.winfo_id()
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020

        user32 = ctypes.windll.user32
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ex_style = ex_style | WS_EX_LAYERED
        if enabled:
            ex_style = ex_style | WS_EX_TRANSPARENT
        else:
            ex_style = ex_style & ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
    except Exception:
        return
