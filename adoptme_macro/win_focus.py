from __future__ import annotations

import os
from ctypes import POINTER, byref, create_unicode_buffer, sizeof, windll
from ctypes.wintypes import BOOL, DWORD, HANDLE, HWND, LPWSTR
from typing import Optional


def foreground_process_name() -> Optional[str]:
    hwnd: HWND = windll.user32.GetForegroundWindow()
    if not hwnd:
        return None

    pid = DWORD()
    windll.user32.GetWindowThreadProcessId(hwnd, byref(pid))
    if not pid.value:
        return None

    process = windll.kernel32.OpenProcess(0x1000 | 0x0400, False, pid.value)
    if not process:
        return None

    try:
        buf_len = DWORD(260)
        buf = create_unicode_buffer(buf_len.value)
        if not windll.kernel32.QueryFullProcessImageNameW(process, 0, buf, byref(buf_len)):
            return None
        return os.path.basename(buf.value)
    finally:
        windll.kernel32.CloseHandle(process)


def is_foreground_process(exe_name: str) -> bool:
    name = foreground_process_name()
    if not name:
        return False
    return name.lower() == exe_name.lower()
