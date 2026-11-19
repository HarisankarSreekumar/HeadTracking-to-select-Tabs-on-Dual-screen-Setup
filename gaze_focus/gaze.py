"""Pure geometry: head yaw and eye offset from face landmarks.

Only the *relative* angle between the two monitors matters (calibration learns
where each one is), so the absolute sign convention is just kept consistent.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

# Generic 3D face model in millimetres, in camera-aligned axes
# (x = image right, y = image down, z = away from camera). Order matches
# LANDMARK_IDS: nose tip, chin, image-right eye outer corner, image-left eye
# outer corner, image-right mouth corner, image-left mouth corner.
MODEL_POINTS = np.array(
    [
        [0.0, 0.0, 0.0],
        [0.0, 330.0, 65.0],
        [225.0, -170.0, 135.0],
        [-225.0, -170.0, 135.0],
        [150.0, 150.0, 125.0],
        [-150.0, 150.0, 125.0],
    ],
    dtype=np.float64,
)

# MediaPipe Face Mesh indices for the points above.
LANDMARK_IDS = (1, 152, 263, 33, 291, 61)


def head_yaw_deg(image_points: np.ndarray, frame_w: int, frame_h: int) -> float:
    """Head yaw in degrees from the 6 image points (pixels) matching MODEL_POINTS."""
    cam = np.array(
        [[frame_w, 0, frame_w / 2], [0, frame_w, frame_h / 2], [0, 0, 1]],
        dtype=np.float64,
    )
    ok, rvec, _ = cv2.solvePnP(
        MODEL_POINTS,
        np.asarray(image_points, dtype=np.float64).reshape(-1, 1, 2),
        cam,
        np.zeros(4),
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not ok:
        return 0.0
    rot, _ = cv2.Rodrigues(rvec)
    # For a rotation about the camera Y axis, R[0, 2] == sin(angle).
    return -math.degrees(math.asin(float(np.clip(rot[0, 2], -1.0, 1.0))))


def iris_offset(eye_outer: np.ndarray, eye_inner: np.ndarray, iris: np.ndarray) -> float:
    """Where the iris sits between the eye corners: -1 (outer) .. 0 (centre) .. 1 (inner)."""
    a = np.asarray(eye_outer, dtype=np.float64)
    b = np.asarray(eye_inner, dtype=np.float64)
    axis = b - a
    length_sq = float(axis @ axis)
    if length_sq == 0.0:
        return 0.0
    t = float((np.asarray(iris, dtype=np.float64) - a) @ axis) / length_sq
    return float(np.clip(2.0 * t - 1.0, -1.0, 1.0))


def combined_gaze(
    head_yaw: float, eye_offset: float, eye_weight: float, eye_range_deg: float = 15.0
) -> float:
    """Head yaw plus a weighted contribution from where the eyes point."""
    return head_yaw + eye_weight * eye_offset * eye_range_deg
