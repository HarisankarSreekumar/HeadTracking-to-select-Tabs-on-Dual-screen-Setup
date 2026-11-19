from gaze_focus.config import Config
from gaze_focus.gaze import GazeSample as S
from gaze_focus.controller import CameraLoop, Controller
from gaze_focus.windows import WindowInfo

W1 = WindowInfo(1, "Editor", "M1", True, False, False, False)
W2 = WindowInfo(2, "Browser", "M2", True, False, False, False)


class Fakes:
    def __init__(self, monitors=("M1", "M2"), fg="M1"):
        self.monitors = list(monitors)
        self.fg = fg
        self.focused = []

    def controller(self):
        cfg = Config(dwell_s=0.5, smoothing_frames=1, calibration={"M1": -20.0, "M2": 20.0}, pitch_baseline=0.0)
        return Controller(
            cfg,
            current_monitors=lambda: self.monitors,
            list_windows=lambda: [W1, W2],
            foreground_monitor=lambda: self.fg,
            focus_window=lambda h: self.focused.append(h) or True,
        )


def test_switches_after_dwell():
    f = Fakes()
    c = f.controller()
    assert c.on_gaze(S(20, 0), 0.0) is None
    assert c.on_gaze(S(20, 0), 0.6) == W2.hwnd
    assert f.focused == [W2.hwnd]
    assert c.status == "running"


def test_face_lost_resets_and_never_focuses():
    f = Fakes()
    c = f.controller()
    assert c.on_gaze(S(20, 0), 0.0) is None
    assert c.on_gaze(None, 0.3) is None
    assert c.on_gaze(S(20, 0), 0.6) is None
    assert f.focused == []


def test_no_focus_when_foreground_already_on_target():
    f = Fakes(fg="M2")
    c = f.controller()
    c.on_gaze(S(20, 0), 0.0)
    assert c.on_gaze(S(20, 0), 0.6) is None
    assert f.focused == []


def test_paused_does_nothing():
    f = Fakes()
    c = f.controller()
    c.toggle_pause()
    for t in (0.0, 0.5, 1.0):
        assert c.on_gaze(S(20, 0), t) is None
    assert c.status == "paused"
    assert f.focused == []


def test_unknown_monitors_requires_recalibration():
    f = Fakes(monitors=("M1", "M3"))
    c = f.controller()
    c.on_gaze(S(20, 0), 0.0)
    assert c.on_gaze(S(20, 0), 1.0) is None
    assert c.status == "needs_calibration"
    assert f.focused == []


def test_camera_open_failure_retries():
    t = [0.0]
    attempts = []
    c = Fakes().controller()

    def open_tracker():
        attempts.append(t[0])
        return None

    loop = CameraLoop(open_tracker, c, clock=lambda: t[0], retry_s=5.0)
    loop.step()
    assert c.status == "no_camera"
    assert len(attempts) == 1
    t[0] = 2.0
    loop.step()
    assert len(attempts) == 1
    t[0] = 5.1
    loop.step()
    assert len(attempts) == 2


def test_camera_lost_mid_session_reopens():
    t = [0.0]
    opened = []

    class FakeTracker:
        is_open = True

        def read_gaze(self, eye_weight):
            return None

    def open_tracker():
        tr = FakeTracker()
        opened.append(tr)
        return tr

    loop = CameraLoop(open_tracker, Fakes().controller(), clock=lambda: t[0], retry_s=5.0)
    loop.step()
    assert len(opened) == 1
    opened[0].is_open = False  # tracker closed itself after repeated read failures
    t[0] = 1.0
    loop.step()
    assert loop.controller.status == "no_camera"
    t[0] = 6.5
    loop.step()
    assert len(opened) == 2


def test_loop_records_last_gaze_for_debug_output():
    class FakeTracker:
        is_open = True

        def read_gaze(self, eye_weight):
            return S(12.5, 0)

    loop = CameraLoop(lambda: FakeTracker(), Fakes().controller(), clock=lambda: 0.0)
    loop.step()
    assert loop.last_gaze == S(12.5, 0)


def test_looking_down_at_phone_never_focuses():
    f = Fakes()
    c = f.controller()
    # face still tracked, head turned slightly toward M2 but pitched far down
    for t in (0.0, 0.3, 0.6, 1.0):
        assert c.on_gaze(S(20, 35), t) is None
    assert f.focused == []
    # looking back up at M2 switches normally after a fresh dwell
    assert c.on_gaze(S(20, 5), 1.1) is None
    assert c.on_gaze(S(20, 5), 1.7) == W2.hwnd
