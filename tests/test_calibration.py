import pytest

from gaze_focus.calibration import CalibrationError, compute_calibration, run_calibration
from gaze_focus.gaze import GazeSample


def test_compute_median():
    cal = compute_calibration({"A": [-21, -20, -19] * 10, "B": [18, 19, 20] * 10})
    assert cal == {"A": -20, "B": 19}


def test_too_few_samples():
    with pytest.raises(CalibrationError):
        compute_calibration({"A": [-20] * 5, "B": [20] * 30})


def test_too_close():
    with pytest.raises(CalibrationError):
        compute_calibration({"A": [-2] * 30, "B": [3] * 30})


def test_run_calibration_with_fakes():
    t = [0.0]
    prompts = []

    def clock():
        return t[0]

    def read_gaze():
        t[0] += 0.1
        return GazeSample(-20.0, 9.0) if len(prompts) == 1 else GazeSample(20.0, 11.0)

    result = run_calibration(read_gaze, ["M1", "M2"], prompts.append, seconds=3.0, clock=clock)
    assert result.monitors == pytest.approx({"M1": -20.0, "M2": 20.0})
    assert result.pitch_baseline == pytest.approx(10.0, abs=1.0)
    assert len(prompts) == 2
