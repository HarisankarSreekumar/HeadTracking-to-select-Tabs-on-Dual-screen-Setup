"""Pure window-selection logic (no Win32 imports)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    monitor: str
    visible: bool
    minimized: bool
    tool_window: bool
    cloaked: bool


def pick_window(windows_zorder: list[WindowInfo], target_monitor: str) -> WindowInfo | None:
    """First eligible window on ``target_monitor``, given windows top-to-bottom in Z-order."""
    for win in windows_zorder:
        if (
            win.monitor == target_monitor
            and win.visible
            and not win.minimized
            and not win.tool_window
            and not win.cloaked
            and win.title
        ):
            return win
    return None
