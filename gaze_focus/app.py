"""Windows tray app: camera thread + tray icon + global pause hotkey."""
from __future__ import annotations

import argparse
import ctypes
import logging
import threading
import time
from typing import Callable

from .calibration import CalibrationError, describe_monitors, run_calibration
from .config import default_config_path, load_config, save_config
from .controller import CameraLoop, Controller

FRAME_INTERVAL_S = 1 / 20  # cap at ~20 fps to keep CPU low
_STATUS_TEXT = {
    "running": "Gaze Focus: running",
    "paused": "Gaze Focus: paused",
    "needs_calibration": "Gaze Focus: monitors changed - choose Recalibrate",
    "no_camera": "Gaze Focus: webcam unavailable - retrying",
    "error": "Gaze Focus: camera error - retrying",
}
_STATUS_COLOR = {
    "running": (46, 160, 67),
    "paused": (150, 150, 150),
    "needs_calibration": (230, 160, 0),
    "no_camera": (210, 50, 50),
    "error": (210, 50, 50),
}


class StatusDisplay:
    """Calls ``apply`` only when the status actually changes (redrawing the tray
    icon every frame costs a temp file + two Explorer round-trips each time)."""

    def __init__(self, apply: Callable[[str], None]) -> None:
        self._apply = apply
        self._last: str | None = None

    def update(self, status: str) -> None:
        if status != self._last:
            self._last = status
            self._apply(status)


def _message(text: str, error: bool = False) -> None:
    MB_OK, MB_ICONINFO, MB_ICONERROR, MB_TOPMOST = 0x0, 0x40, 0x10, 0x40000
    flags = MB_OK | MB_TOPMOST | (MB_ICONERROR if error else MB_ICONINFO)
    ctypes.windll.user32.MessageBoxW(None, text, "Gaze Focus", flags)


def _icon_image(status: str):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 16, 60, 48), fill=(255, 255, 255, 255), outline=(40, 40, 40, 255), width=3)
    d.ellipse((22, 22, 42, 42), fill=_STATUS_COLOR.get(status, (0, 0, 0)) + (255,))
    return img


def main() -> None:
    import keyboard
    import pystray

    from . import win32_adapter as w32
    from .tracker import FaceTracker

    parser = argparse.ArgumentParser(prog="gaze_focus")
    parser.add_argument("--debug", action="store_true", help="print gaze angle and status twice a second")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING)

    path = default_config_path()
    cfg = load_config(path)
    controller = Controller(cfg, w32.list_monitors, w32.list_windows, w32.foreground_monitor, w32.focus_window)

    def open_tracker():
        tr = FaceTracker(cfg.camera_index)
        try:
            return tr if tr.open() else None
        except Exception as exc:  # model download failure, camera driver errors
            if args.debug:
                print("camera/model error:", exc)
            return None

    loop = CameraLoop(open_tracker, controller)
    stop = threading.Event()
    want_calibration = threading.Event()
    if controller.status == "needs_calibration" or set(cfg.calibration) != set(w32.list_monitors()):
        want_calibration.set()

    def calibrate() -> None:
        if loop.tracker is None:
            _message("Can't calibrate: the webcam isn't available. Close other apps using it and try again.", True)
            return
        monitors = w32.list_monitors()
        try:
            result = run_calibration(
                lambda: loop.tracker.read_gaze(cfg.eye_weight),
                monitors,
                _message,
                labels=describe_monitors(w32.monitor_rects()),
            )
        except CalibrationError as exc:
            _message(f"Calibration failed.\n\n{exc}", True)
            controller.recalibrated(cfg.calibration, cfg.pitch_baseline)
            return
        controller.recalibrated(result.monitors, result.pitch_baseline)
        save_config(cfg, path)
        _message("Calibration saved. Gaze Focus is running.")

    def worker() -> None:
        last_debug = 0.0
        while not stop.is_set():
            started = time.monotonic()
            if want_calibration.is_set() and loop.tracker is not None:
                want_calibration.clear()
                try:
                    calibrate()
                except Exception as exc:  # keep the camera thread alive
                    _message(f"Calibration failed unexpectedly: {exc}", True)
            loop.step()
            if args.debug and started - last_debug > 0.5:
                last_debug = started
                print(f"status={controller.status} gaze={loop.last_gaze}")
            display.update(controller.status)
            time.sleep(max(0.0, FRAME_INTERVAL_S - (time.monotonic() - started)))
        if loop.tracker is not None:
            loop.tracker.close()

    images = {}

    def show_status(status: str) -> None:
        if status not in images:
            images[status] = _icon_image(status)
        icon.icon = images[status]
        icon.title = _STATUS_TEXT.get(status, status)
        icon.update_menu()

    display = StatusDisplay(show_status)

    def on_toggle(_icon=None, _item=None) -> None:
        controller.toggle_pause()

    def on_recalibrate(_icon=None, _item=None) -> None:
        want_calibration.set()

    def on_quit(_icon=None, _item=None) -> None:
        stop.set()
        keyboard.unhook_all()
        icon.stop()

    icon = pystray.Icon(
        "gaze_focus",
        _icon_image(controller.status),
        _STATUS_TEXT["running"],
        menu=pystray.Menu(
            pystray.MenuItem(lambda _: "Resume" if controller.paused else "Pause", on_toggle, default=True),
            pystray.MenuItem("Recalibrate", on_recalibrate),
            pystray.MenuItem("Quit", on_quit),
        ),
    )
    keyboard.add_hotkey(cfg.hotkey, on_toggle)
    # Hold off switching while the user is typing. Only the time is recorded.
    keyboard.on_press(lambda _e: controller.note_keypress(time.monotonic()))
    thread = threading.Thread(target=worker, name="gaze-focus-camera", daemon=True)
    thread.start()
    icon.run()
    stop.set()
    thread.join(timeout=2)
