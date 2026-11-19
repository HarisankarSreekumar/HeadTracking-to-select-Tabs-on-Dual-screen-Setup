import pytest

from gaze_focus.classifier import DwellGate, MonitorClassifier, Smoother


def test_smoother_mean():
    s = Smoother(3)
    for x in (0, 3, 6):
        s.update(x)
    assert s.update(9) == 6.0
    s.reset()
    assert s.update(10) == 10.0


def test_classify_basic():
    c = MonitorClassifier({"L": -20, "R": 20}, 3)
    assert c.classify(-15) == "L"
    c.reset()
    assert c.classify(15) == "R"


def test_classify_hysteresis():
    c = MonitorClassifier({"L": -20, "R": 20}, 3)
    assert c.classify(-15) == "L"
    assert c.classify(2) == "L"
    assert c.classify(4) == "R"
    assert c.classify(-2) == "R"
    assert c.classify(-4) == "L"


def test_classify_first_reading_inside_band_uses_midpoint():
    c = MonitorClassifier({"L": -20, "R": 20}, 3)
    assert c.classify(1) == "R"


def test_classify_requires_two_monitors():
    with pytest.raises(ValueError):
        MonitorClassifier({"L": 0}, 3)


def test_dwell_fires_once_after_dwell():
    d = DwellGate(0.5)
    assert d.update("R", 0.0) is None
    assert d.update("R", 0.4) is None
    assert d.update("R", 0.5) == "R"
    assert d.update("R", 0.9) is None


def test_dwell_glance_ignored():
    d = DwellGate(0.5)
    assert d.update("R", 0.0) is None
    assert d.update("R", 0.3) is None
    assert d.update("L", 0.35) is None
    assert d.update("R", 0.6) is None


def test_dwell_none_resets():
    d = DwellGate(0.5)
    assert d.update("R", 0.0) is None
    assert d.update(None, 0.3) is None
    assert d.update("R", 0.4) is None
    assert d.update("R", 0.9) == "R"
