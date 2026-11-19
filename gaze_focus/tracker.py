"""Webcam + MediaPipe Face Landmarker -> one gaze angle per frame.

Heavy imports (cv2 capture, mediapipe) happen in ``open()`` so this module can
be imported anywhere.
"""
from __future__ import annotations

import time
import urllib.request
from pathlib import Path

import numpy as np

from .config import default_config_path
from .gaze import LANDMARK_IDS, GazeSample, combined_gaze, head_pose_deg, iris_offset

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)

MAX_READ_FAILURES = 30

# Eye landmarks, each pair ordered image-left -> image-right so that a positive
# offset means "looking toward image right" for both eyes (same direction as a
# positive head yaw). Do NOT mirror the camera frame, or this flips.
_RIGHT_EYE = (33, 133, 468)  # subject's right eye: image-left corner, image-right corner, iris
_LEFT_EYE = (362, 263, 473)  # subject's left eye


def model_path() -> Path:
    return default_config_path().parent / "face_landmarker.task"


def ensure_model(path: Path | None = None) -> Path:
    path = path or model_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(MODEL_URL, tmp)
        tmp.replace(path)
    return path


def gaze_from_landmarks(
    points_px: np.ndarray, frame_w: int, frame_h: int, eye_weight: float
) -> GazeSample | None:
    """points_px: (N, 2) pixel coords of all Face Mesh landmarks (N >= 478)."""
    pose = head_pose_deg(points_px[list(LANDMARK_IDS)], frame_w, frame_h)
    if pose is None:
        return None
    offsets = [iris_offset(points_px[a], points_px[b], points_px[i]) for a, b, i in (_RIGHT_EYE, _LEFT_EYE)]
    return GazeSample(combined_gaze(pose.yaw, sum(offsets) / 2.0, eye_weight), pose.pitch)


class FaceTracker:
    def __init__(self, camera_index: int) -> None:
        self.camera_index = camera_index
        self._cap = None
        self._landmarker = None
        self._t0 = time.monotonic()
        self._last_ts = -1
        self._read_failures = 0

    def open(self) -> bool:
        import cv2
        from mediapipe.tasks.python import BaseOptions, vision

        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW) if hasattr(cv2, "CAP_DSHOW") else None
        if cap is None or not cap.isOpened():
            cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            return False
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(ensure_model())),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self._cap = cap
        return True

    def read_gaze(self, eye_weight: float) -> GazeSample | None:
        import cv2
        import mediapipe as mp

        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        if not ok or frame is None:
            self._read_failures += 1
            if self._read_failures >= MAX_READ_FAILURES:
                self.close()  # camera unplugged / taken by another app; CameraLoop reopens it
            return None
        self._read_failures = 0
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        ts = int((time.monotonic() - self._t0) * 1000)
        ts = max(ts, self._last_ts + 1)  # VIDEO mode needs strictly increasing timestamps
        self._last_ts = ts
        result = self._landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)
        if not result.face_landmarks:
            return None
        pts = np.array([[p.x * w, p.y * h] for p in result.face_landmarks[0]], dtype=np.float64)
        if len(pts) < 478:
            return None
        return gaze_from_landmarks(pts, w, h, eye_weight)

    @property
    def is_open(self) -> bool:
        return self._cap is not None

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None
