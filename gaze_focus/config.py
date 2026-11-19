"""User settings, persisted as JSON."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


@dataclass
class Config:
    dwell_s: float = 0.5
    hysteresis_deg: float = 3.0
    smoothing_frames: int = 5
    eye_weight: float = 0.5
    hotkey: str = "ctrl+alt+g"
    camera_index: int = 0
    calibration: dict[str, float] = field(default_factory=dict)
    pitch_baseline: float | None = None
    max_pitch_dev_deg: float = 20.0


def default_config_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "GazeFocus" / "config.json"
    return Path.home() / ".gaze_focus" / "config.json"


def load_config(path: Path) -> Config:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Config()
    if not isinstance(data, dict):
        return Config()
    known = {f.name for f in fields(Config)}
    try:
        return Config(**{k: v for k, v in data.items() if k in known})
    except TypeError:
        return Config()


def save_config(cfg: Config, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
