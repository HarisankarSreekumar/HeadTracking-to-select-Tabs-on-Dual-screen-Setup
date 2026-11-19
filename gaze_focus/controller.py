"""Glue between gaze readings and window focus. Pure: all OS calls are injected."""
from __future__ import annotations

import time
from typing import Callable, Protocol

from .classifier import DwellGate, MonitorClassifier, Smoother
from .config import Config
from .windows import WindowInfo, pick_window


class Controller:
    def __init__(
        self,
        cfg: Config,
        current_monitors: Callable[[], list[str]],
        list_windows: Callable[[], list[WindowInfo]],
        foreground_monitor: Callable[[], str | None],
        focus_window: Callable[[int], bool],
    ) -> None:
        self.cfg = cfg
        self._current_monitors = current_monitors
        self._list_windows = list_windows
        self._foreground_monitor = foreground_monitor
        self._focus_window = focus_window
        self._smoother = Smoother(cfg.smoothing_frames)
        self._dwell = DwellGate(cfg.dwell_s)
        self._classifier: MonitorClassifier | None = None
        self.paused = False
        self.status = "running"
        self.recalibrated(cfg.calibration)

    def recalibrated(self, calibration: dict[str, float]) -> None:
        self.cfg.calibration = dict(calibration)
        try:
            self._classifier = MonitorClassifier(calibration, self.cfg.hysteresis_deg)
        except ValueError:
            self._classifier = None
        self._reset()
        if not self.paused:
            self.status = "running" if self._classifier else "needs_calibration"

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self._reset()
        self.status = "paused" if self.paused else "running"

    def _reset(self) -> None:
        self._smoother.reset()
        self._dwell.reset()
        if self._classifier:
            self._classifier.reset()

    def on_gaze(self, gaze: float | None, now: float) -> int | None:
        if self.paused:
            self.status = "paused"
            return None
        if self._classifier is None or set(self.cfg.calibration) != set(self._current_monitors()):
            self.status = "needs_calibration"
            self._reset()
            return None
        self.status = "running"
        if gaze is None:
            self._reset()
            return None
        target = self._dwell.update(self._classifier.classify(self._smoother.update(gaze)), now)
        if target is None or self._foreground_monitor() == target:
            return None
        win = pick_window(self._list_windows(), target)
        if win is None or not self._focus_window(win.hwnd):
            return None
        return win.hwnd


class Tracker(Protocol):
    is_open: bool

    def read_gaze(self, eye_weight: float) -> float | None: ...


class CameraLoop:
    """One iteration per frame; (re)opens the camera every ``retry_s`` while it's unavailable."""

    def __init__(
        self,
        open_tracker: Callable[[], Tracker | None],
        controller: Controller,
        clock: Callable[[], float] = time.monotonic,
        retry_s: float = 5.0,
    ) -> None:
        self._open_tracker = open_tracker
        self.controller = controller
        self._clock = clock
        self._retry_s = retry_s
        self.tracker: Tracker | None = None
        self.last_gaze: float | None = None
        self._next_attempt = float("-inf")

    def step(self) -> None:
        now = self._clock()
        if self.tracker is not None and not getattr(self.tracker, "is_open", True):
            self.tracker = None
            self.controller.status = "no_camera"
            self._next_attempt = now + self._retry_s
            return
        if self.tracker is None:
            if now < self._next_attempt:
                return
            self.tracker = self._open_tracker()
            if self.tracker is None:
                self.controller.status = "no_camera"
                self._next_attempt = now + self._retry_s
                return
        self.last_gaze = self.tracker.read_gaze(self.controller.cfg.eye_weight)
        self.controller.on_gaze(self.last_gaze, now)
