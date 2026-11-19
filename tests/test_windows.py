from gaze_focus.windows import WindowInfo, pick_window


def w(hwnd, monitor, title="t", visible=True, minimized=False, tool_window=False, cloaked=False):
    return WindowInfo(hwnd, title, monitor, visible, minimized, tool_window, cloaked)


def test_pick_topmost_on_target():
    wins = [w(1, "M1"), w(2, "M2"), w(3, "M2")]
    assert pick_window(wins, "M2").hwnd == 2


def test_pick_skips_ineligible():
    wins = [
        w(10, "M2", minimized=True),
        w(11, "M2", tool_window=True),
        w(12, "M2", cloaked=True),
        w(13, "M2", title=""),
        w(14, "M2", visible=False),
        w(15, "M2"),
    ]
    assert pick_window(wins, "M2").hwnd == 15


def test_pick_window_none_when_monitor_empty():
    assert pick_window([w(1, "M1"), w(2, "M1")], "M2") is None
