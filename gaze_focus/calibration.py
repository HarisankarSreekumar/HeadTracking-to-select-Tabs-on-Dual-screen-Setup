"""Learn the gaze angle for each monitor."""
from __future__ import annotations

import statistics
import time
from typing import Callable


class CalibrationError(Exception):
    """Calibration failed; the message is shown to the user."""


def compute_calibration(
    samples: dict[str, list[float]], min_samples: int = 20, min_separation_deg: float = 8.0
) -> dict[str, float]:
    if len(samples) != 2:
        raise CalibrationError(f"Gaze Focus needs exactly 2 monitors; found {len(samples)}.")
    for name, values in samples.items():
        if len(values) < min_samples:
            raise CalibrationError(
                f"Couldn't see your face clearly while you looked at {name}. "
                "Check the webcam faces you and the room is lit, then try again."
            )
    cal = {name: statistics.median(values) for name, values in samples.items()}
    a, b = cal.values()
    if abs(a - b) < min_separation_deg:
        raise CalibrationError(
            "Looking at the two monitors gave almost the same head direction. "
            "Turn your head toward each monitor (not just your eyes) and try again."
        )
    return cal


def run_calibration(
    read_gaze: Callable[[], float | None],
    monitors: list[str],
    prompt: Callable[[str], None],
    seconds: float = 3.0,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, float]:
    samples: dict[str, list[float]] = {}
    for i, name in enumerate(monitors, start=1):
        prompt(
            f"Look at monitor {i} ({name}) the way you normally would while working, "
            f"then press OK and keep looking at it for {seconds:g} seconds."
        )
        values: list[float] = []
        end = clock() + seconds
        while clock() < end:
            g = read_gaze()
            if g is not None:
                values.append(g)
        samples[name] = values
    return compute_calibration(samples)
