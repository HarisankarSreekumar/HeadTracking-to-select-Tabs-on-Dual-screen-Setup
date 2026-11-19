import math

import cv2
import numpy as np

from gaze_focus.gaze import MODEL_POINTS, combined_gaze, head_yaw_deg, iris_offset

W, H = 1280, 720


def _project(yaw_deg: float) -> np.ndarray:
    """Project the face model rotated by yaw_deg (user turning right = positive)."""
    cam = np.array([[W, 0, W / 2], [0, W, H / 2], [0, 0, 1]], dtype=np.float64)
    # Camera looks down +Z; face faces the camera. Turning right (user's view)
    # is a rotation about the camera's Y axis by -yaw.
    rvec = np.array([0.0, -math.radians(yaw_deg), 0.0])
    tvec = np.array([0.0, 0.0, 600.0])
    pts, _ = cv2.projectPoints(MODEL_POINTS, rvec, tvec, cam, np.zeros(4))
    return pts.reshape(-1, 2)


def test_head_yaw_frontal_near_zero():
    assert abs(head_yaw_deg(_project(0), W, H)) < 2


def test_head_yaw_recovers_rotation():
    for yaw in (25.0, -25.0):
        got = head_yaw_deg(_project(yaw), W, H)
        assert abs(got - yaw) < 3, (yaw, got)


def test_iris_offset_centre_and_edges():
    outer, inner = np.array([0.0, 0.0]), np.array([10.0, 0.0])
    assert iris_offset(outer, inner, np.array([5.0, 0.0])) == 0.0
    assert iris_offset(outer, inner, np.array([10.0, 0.0])) == 1.0
    assert iris_offset(outer, inner, np.array([0.0, 0.0])) == -1.0
    assert iris_offset(outer, inner, np.array([15.0, 0.0])) == 1.0


def test_combined_gaze():
    assert combined_gaze(10, 0.5, 0.5) == 13.75
