"""Turn a stream of gaze angles into a settled target monitor."""
from __future__ import annotations

from collections import deque


class Smoother:
    """Moving average over the last n readings."""

    def __init__(self, n: int) -> None:
        self._buf: deque[float] = deque(maxlen=max(1, int(n)))

    def update(self, x: float) -> float:
        self._buf.append(float(x))
        return sum(self._buf) / len(self._buf)

    def reset(self) -> None:
        self._buf.clear()


class MonitorClassifier:
    """Decides which of two calibrated monitors a gaze yaw points at.

    The split is the midpoint between the two calibrated yaws. Once a monitor
    is chosen, the gaze must cross the midpoint by more than ``hysteresis_deg``
    before the choice changes, so looking near the boundary doesn't flap.
    """

    def __init__(self, calibration: dict[str, float], hysteresis_deg: float) -> None:
        if len(calibration) != 2:
            raise ValueError("exactly two calibrated monitors are required")
        (self._low, low_yaw), (self._high, high_yaw) = sorted(
            calibration.items(), key=lambda kv: kv[1]
        )
        self._mid = (low_yaw + high_yaw) / 2.0
        self._hyst = float(hysteresis_deg)
        self._current: str | None = None

    def classify(self, gaze_yaw: float) -> str | None:
        if self._current is None:
            self._current = self._high if gaze_yaw >= self._mid else self._low
        elif self._current == self._low and gaze_yaw > self._mid + self._hyst:
            self._current = self._high
        elif self._current == self._high and gaze_yaw < self._mid - self._hyst:
            self._current = self._low
        return self._current

    def reset(self) -> None:
        self._current = None


class DwellGate:
    """Fires a target once it has been held continuously for ``dwell_s``."""

    def __init__(self, dwell_s: float) -> None:
        self._dwell = float(dwell_s)
        self.reset()

    def update(self, target: str | None, now: float) -> str | None:
        if target is None:
            self.reset()
            return None
        if target != self._candidate:
            self._candidate, self._since, self._fired = target, now, False
            return None
        if not self._fired and now - self._since >= self._dwell:
            self._fired = True
            return target
        return None

    def reset(self) -> None:
        self._candidate: str | None = None
        self._since = 0.0
        self._fired = False
