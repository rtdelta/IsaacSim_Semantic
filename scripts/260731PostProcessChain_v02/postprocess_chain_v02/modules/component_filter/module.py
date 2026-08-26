from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .config import ComponentFilterConfig


@dataclass(frozen=True)
class ComponentFilterResult:
    mask: np.ndarray
    raw_pixel_count: int
    clean_pixel_count: int
    kept_component_count: int
    removed_component_count: int
    removed_pixel_count: int


def filter_connected_components(
    mask: np.ndarray,
    config: ComponentFilterConfig,
) -> ComponentFilterResult:
    """Keep every same-label 4-connected component meeting the size threshold."""
    if mask.ndim != 2:
        raise ValueError(f"component mask must be 2D, got shape={mask.shape}")
    raw_mask = np.ascontiguousarray(mask, dtype=np.bool_)
    raw_pixel_count = int(np.count_nonzero(raw_mask))
    if config.connectivity != 4:
        raise ValueError("component filter connectivity must be 4")
    if raw_pixel_count == 0:
        return ComponentFilterResult(
            mask=raw_mask,
            raw_pixel_count=0,
            clean_pixel_count=0,
            kept_component_count=0,
            removed_component_count=0,
            removed_pixel_count=0,
        )
    if not config.enabled:
        component_count, _labels = cv2.connectedComponents(
            raw_mask.astype(np.uint8, copy=False),
            connectivity=4,
            ltype=cv2.CV_32S,
        )
        return ComponentFilterResult(
            mask=raw_mask,
            raw_pixel_count=raw_pixel_count,
            clean_pixel_count=raw_pixel_count,
            kept_component_count=component_count - 1,
            removed_component_count=0,
            removed_pixel_count=0,
        )
    component_count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        raw_mask.astype(np.uint8, copy=False),
        connectivity=4,
        ltype=cv2.CV_32S,
    )
    sizes = np.asarray(stats[1:, cv2.CC_STAT_AREA], dtype=np.int64)
    keep = sizes >= config.minimum_connected_component_pixels
    kept_labels = np.flatnonzero(keep).astype(np.int32) + 1
    if kept_labels.size:
        clean_mask = np.isin(labels, kept_labels)
    else:
        clean_mask = np.zeros(raw_mask.shape, dtype=np.bool_)
    clean_pixel_count = int(sizes[keep].sum(dtype=np.int64))
    removed_pixel_count = raw_pixel_count - clean_pixel_count
    actual_component_count = component_count - 1
    kept_component_count = int(np.count_nonzero(keep))
    return ComponentFilterResult(
        mask=np.ascontiguousarray(clean_mask, dtype=np.bool_),
        raw_pixel_count=raw_pixel_count,
        clean_pixel_count=clean_pixel_count,
        kept_component_count=kept_component_count,
        removed_component_count=actual_component_count - kept_component_count,
        removed_pixel_count=removed_pixel_count,
    )
