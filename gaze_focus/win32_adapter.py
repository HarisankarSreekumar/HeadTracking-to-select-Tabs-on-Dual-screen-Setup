"""Thin Win32 layer (ctypes only). Windows-only; never imported by tests."""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from .windows import WindowInfo

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")
kernel32 = ctypes.WinDLL("kernel32")

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
MONITOR_DEFAULTTONEAREST = 2
DWMWA_CLOAKED = 14
VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x0002

# Shell windows that are "visible with a title" but should never get focus.
_SKIP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


MonitorEnumProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
)
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

user32.MonitorFromWindow.restype = wintypes.HMONITOR
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]


def _monitor_name(hmon) -> str | None:
    if not hmon:
        return None
    info = MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(MONITORINFOEXW)
    if not user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
        return None
    return info.szDevice


def _window_monitor(hwnd) -> str | None:
    return _monitor_name(user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST))


def list_monitors() -> list[str]:
    names: list[str] = []

    def cb(hmon, _hdc, _rect, _lparam):
        name = _monitor_name(hmon)
        if name:
            names.append(name)
        return True

    user32.EnumDisplayMonitors(None, None, MonitorEnumProc(cb), 0)
    return names


def _text(hwnd) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _class(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _cloaked(hwnd) -> bool:
    val = ctypes.c_int(0)
    res = dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd), DWMWA_CLOAKED, ctypes.byref(val), ctypes.sizeof(val)
    )
    return res == 0 and val.value != 0


def list_windows() -> list[WindowInfo]:
    """Top-level windows, top-to-bottom in Z-order."""
    out: list[WindowInfo] = []

    def cb(hwnd, _lparam):
        if _class(hwnd) in _SKIP_CLASSES:
            return True
        out.append(
            WindowInfo(
                hwnd=int(hwnd),
                title=_text(hwnd),
                monitor=_window_monitor(hwnd) or "",
                visible=bool(user32.IsWindowVisible(hwnd)),
                minimized=bool(user32.IsIconic(hwnd)),
                tool_window=bool(user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW),
                cloaked=_cloaked(hwnd),
            )
        )
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return out


def foreground_monitor() -> str | None:
    hwnd = user32.GetForegroundWindow()
    return _window_monitor(hwnd) if hwnd else None


def focus_window(hwnd: int) -> bool:
    """Bring ``hwnd`` to the foreground despite Windows' focus-stealing lock."""
    # A synthetic Alt tap counts as user input, which lets this process set the
    # foreground window. Release it *before* switching so the new window
    # doesn't receive a lone Alt-up (which would open its menu bar).
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    if user32.SetForegroundWindow(hwnd):
        return user32.GetForegroundWindow() == hwnd

    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None)
    me = kernel32.GetCurrentThreadId()
    attached = bool(fg_thread and fg_thread != me and user32.AttachThreadInput(me, fg_thread, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(me, fg_thread, False)
    time.sleep(0.01)
    return user32.GetForegroundWindow() == hwnd
