from __future__ import annotations

from typing import Tuple

import numpy as np

from .config import VisibilityRatioConfig


def calculate_visibility(
    whole_counts: np.ndarray,
    reference_counts: np.ndarray,
    config: VisibilityRatioConfig,
) -> Tuple[np.ndarray, np.ndarray]:
    if whole_counts.shape != (5,) or reference_counts.shape != (5,):
        raise ValueError("visibility counts must have shape (5,)")
    ratios = np.full(5, config.zero_reference_value, dtype=np.float64)
    valid = reference_counts > 0
    np.divide(whole_counts, reference_counts, out=ratios, where=valid)
    statuses = np.full(5, "valid", dtype="<U20")
    statuses[~valid] = "reference_missing"
    statuses[valid & (ratios > 1.0)] = "ratio_over_one"
    return ratios, statuses
