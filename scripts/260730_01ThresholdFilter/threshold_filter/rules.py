from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from .config import RunConfig
from .models import RatioMatrix, RuleMasks


def _apply_invalid_policy(
    mask: np.ndarray,
    selected: np.ndarray,
    policy: str,
    quarantine: np.ndarray,
) -> None:
    if not np.any(selected):
        return
    if policy == "error":
        return
    if policy == "keep":
        mask[selected] = False
        return
    if policy == "drop":
        mask[selected] = True
        return
    if policy == "quarantine":
        quarantine[selected] = True
        mask[selected] = False
        return
    raise ValueError(f"unsupported invalid ratio policy: {policy}")


def _error_samples(
    ratios: RatioMatrix,
    selected: np.ndarray,
    kind: str,
    limit: int = 5,
) -> str:
    locations = np.argwhere(selected)
    values = []
    for frame_index, target_index in locations[:limit]:
        values.append(
            f"{ratios.frame_ids[int(frame_index)]}/"
            f"{ratios.labels[int(target_index)]}"
        )
    suffix = (
        f" (and {len(locations) - limit} more)"
        if len(locations) > limit
        else ""
    )
    return f"{kind}: {', '.join(values)}{suffix}"


def build_rule_masks(config: RunConfig, ratios: RatioMatrix) -> RuleMasks:
    reference_missing = ratios.statuses == "reference_missing"
    empty_ratio = ratios.statuses == "empty_ratio"
    errors = []
    if (
        config.ratio_handling.reference_missing == "error"
        and np.any(reference_missing)
    ):
        errors.append(_error_samples(ratios, reference_missing, "reference_missing"))
    if config.ratio_handling.empty_ratio == "error" and np.any(empty_ratio):
        errors.append(_error_samples(ratios, empty_ratio, "empty_ratio"))
    if errors:
        raise ValueError("invalid ratios encountered; " + "; ".join(errors))

    valid = np.isfinite(ratios.ratios)
    single_drop = valid & (
        ratios.ratios < config.rules.single_tooth.minimum_visible_ratio
    )
    group_low = valid & (
        ratios.ratios < config.rules.tooth_group.minimum_visible_ratio
    )
    quarantine_entries = np.zeros(ratios.ratios.shape, dtype=np.bool_)

    for selected, policy in (
        (reference_missing, config.ratio_handling.reference_missing),
        (empty_ratio, config.ratio_handling.empty_ratio),
    ):
        _apply_invalid_policy(single_drop, selected, policy, quarantine_entries)
        _apply_invalid_policy(group_low, selected, policy, quarantine_entries)

    group_low_counts = group_low.sum(axis=1, dtype=np.int16)
    group_drop = (
        group_low_counts >= config.rules.tooth_group.minimum_low_teeth
    )
    legacy_eligible = (
        ratios.whole_counts
        >= config.identity.legacy_zero_class_order.source_min_pixels
    )
    quarantine_frames = quarantine_entries.any(axis=1)
    return RuleMasks(
        single_drop=np.asarray(single_drop, dtype=np.bool_),
        group_low=np.asarray(group_low, dtype=np.bool_),
        group_low_counts=np.asarray(group_low_counts, dtype=np.int16),
        group_drop=np.asarray(group_drop, dtype=np.bool_),
        legacy_eligible=np.asarray(legacy_eligible, dtype=np.bool_),
        quarantine_frames=np.asarray(quarantine_frames, dtype=np.bool_),
    )
