from __future__ import annotations

import numpy as np

from .config import SingleToothBoxesConfig


def build_source_box_mask(
    whole_counts: np.ndarray,
    full_geometry_valid: np.ndarray,
    config: SingleToothBoxesConfig,
) -> np.ndarray:
    if whole_counts.shape != (5,) or full_geometry_valid.shape != (5,):
        raise ValueError("single-tooth inputs must have shape (5,)")
    return np.asarray(
        full_geometry_valid & (whole_counts >= config.minimum_pixels),
        dtype=np.bool_,
    )
