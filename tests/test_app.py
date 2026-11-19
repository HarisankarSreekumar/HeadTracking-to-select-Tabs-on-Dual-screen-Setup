from gaze_focus.app import StatusDisplay


def test_tray_redrawn_only_when_status_changes():
    applied = []
    d = StatusDisplay(applied.append)
    for s in ["running"] * 20 + ["paused"] * 5 + ["running"]:
        d.update(s)
    assert applied == ["running", "paused", "running"]
