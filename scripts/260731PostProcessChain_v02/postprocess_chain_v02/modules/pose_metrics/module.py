from __future__ import annotations

from typing import Tuple

import numpy as np

from ..semantic_features.models import SceneFeatures
from .config import PoseMetricsConfig


def _require_cv2():
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "pose_metrics requires opencv-python-headless; "
            "install the project requirements"
        ) from exc
    return cv2


def _pixel_cell_corners(coordinates: np.ndarray) -> np.ndarray:
    base = coordinates.astype(np.float32, copy=False)
    offsets = np.asarray(
        ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)),
        dtype=np.float32,
    )
    return (base[:, None, :] + offsets[None, :, :]).reshape(-1, 2)


def calculate_pose_metrics(
    reference: SceneFeatures,
    config: PoseMetricsConfig,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    cv2 = _require_cv2()
    fill = np.full(5, config.invalid_value, dtype=np.float64)
    aspect = np.full(5, config.invalid_value, dtype=np.float64)
    angles = np.full(5, np.nan, dtype=np.float64)
    statuses = np.full(5, "reference_missing", dtype="<U24")

    for index, target in enumerate(reference.targets):
        if target.pixel_count <= 0 or target.coordinates.size == 0:
            continue
        points = _pixel_cell_corners(target.coordinates)
        (_, _), (width, height), angle = cv2.minAreaRect(points)
        width = float(width)
        height = float(height)
        if width <= 0.0 or height <= 0.0:
            statuses[index] = "degenerate_geometry"
            continue
        if width >= height:
            long_side, short_side = width, height
            long_angle = float(angle)
        else:
            long_side, short_side = height, width
            long_angle = float(angle) + 90.0
        area = long_side * short_side
        if area <= 0.0:
            statuses[index] = "degenerate_geometry"
            continue
        raw_fill = float(target.pixel_count) / area
        if raw_fill > 1.0 and raw_fill <= 1.0 + 1e-6:
            raw_fill = 1.0
        if raw_fill < 0.0 or raw_fill > 1.0 + 1e-6:
            statuses[index] = "invalid_fill_ratio"
            continue
        fill[index] = min(raw_fill, 1.0)
        aspect[index] = long_side / short_side
        angles[index] = long_angle % 180.0
        statuses[index] = "valid"
    return fill, aspect, angles, statuses
