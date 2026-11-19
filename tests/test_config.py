import json

from gaze_focus.config import Config, load_config, save_config


def test_load_missing_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "nope.json")
    assert cfg.dwell_s == 0.5
    assert cfg.hotkey == "ctrl+alt+g"
    assert cfg.calibration == {}


def test_roundtrip(tmp_path):
    path = tmp_path / "sub" / "config.json"
    cfg = Config(dwell_s=0.8, calibration={"\\\\.\\DISPLAY1": -20.0, "\\\\.\\DISPLAY2": 18.5})
    save_config(cfg, path)
    assert load_config(path) == cfg


def test_corrupt_file_returns_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json")
    assert load_config(path) == Config()


def test_unknown_keys_ignored(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"foo": 1, "dwell_s": 0.7}))
    cfg = load_config(path)
    assert cfg.dwell_s == 0.7
