from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from threading import BoundedSemaphore
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image

from .artifact_store import ArtifactStore
from .config import RunConfig
from .models import FrameFeatures, FrameTask, InputContract
from .modules.pose_metrics.module import calculate_pose_metrics
from .modules.semantic_features.models import SceneFeatures
from .modules.semantic_features.module import boxes_to_array, extract_semantic_features
from .modules.single_tooth_boxes.module import build_source_box_mask
from .modules.visibility_ratio.module import calculate_visibility


def _load_semantic(path, expected_shape, expected_dtype) -> np.ndarray:
    array = np.load(path, mmap_mode="r", allow_pickle=False)
    if array.ndim != 2 or tuple(array.shape) != tuple(expected_shape):
        raise ValueError(
            f"semantic shape mismatch for {path}: "
            f"expected={expected_shape}, actual={array.shape}"
        )
    if not np.issubdtype(array.dtype, np.integer):
        raise ValueError(f"semantic array must use integer dtype: {path}")
    if expected_dtype and array.dtype != np.dtype(expected_dtype):
        raise ValueError(
            f"semantic dtype mismatch for {path}: "
            f"expected={expected_dtype}, actual={array.dtype}"
        )
    return array


def process_frame(
    task: FrameTask,
    contract: InputContract,
    config: RunConfig,
    reader_slots: BoundedSemaphore,
) -> FrameFeatures:
    with reader_slots:
        full_semantic = _load_semantic(
            task.full_semantic_path, contract.shape, contract.expected_dtype
        )
        reference_semantic = _load_semantic(
            task.reference_semantic_path, contract.shape, contract.expected_dtype
        )
        with Image.open(task.full_rgb_path) as image:
            image_width, image_height = image.size
        if contract.shape != (image_height, image_width):
            raise ValueError(
                f"RGB size mismatch for frame {task.frame_id}: "
                f"semantic={contract.shape}, RGB=({image_width}, {image_height})"
            )

        full_features = extract_semantic_features(
            full_semantic,
            contract.target_ids,
            config.modules.component_filter,
        )
        reference_features = extract_semantic_features(
            reference_semantic,
            contract.target_ids,
            config.modules.component_filter,
        )
        del full_semantic, reference_semantic

    artifacts = ArtifactStore()
    artifacts.put("semantic_features.full", full_features)
    artifacts.put("semantic_features.reference", reference_features)
    full_features = artifacts.get("semantic_features.full", SceneFeatures)
    reference_features = artifacts.get("semantic_features.reference", SceneFeatures)

    whole_counts = full_features.counts
    reference_counts = reference_features.counts
    visibility, statuses = calculate_visibility(
        whole_counts,
        reference_counts,
        config.modules.visibility_ratio,
    )
    fill, aspect, angles, pose_statuses = calculate_pose_metrics(
        reference_features, config.modules.pose_metrics
    )
    full_boxes, full_valid = boxes_to_array(full_features)
    reference_boxes, reference_valid = boxes_to_array(reference_features)
    source_exists = build_source_box_mask(
        whole_counts,
        full_valid,
        config.modules.single_tooth_boxes,
    )
    return FrameFeatures(
        ordinal=task.ordinal,
        frame_id=task.frame_id,
        image_width=image_width,
        image_height=image_height,
        whole_raw_counts=full_features.raw_counts,
        whole_counts=whole_counts,
        reference_raw_counts=reference_features.raw_counts,
        reference_counts=reference_counts,
        full_kept_component_counts=full_features.kept_component_counts,
        full_removed_component_counts=full_features.removed_component_counts,
        full_removed_pixel_counts=full_features.removed_pixel_counts,
        reference_kept_component_counts=reference_features.kept_component_counts,
        reference_removed_component_counts=reference_features.removed_component_counts,
        reference_removed_pixel_counts=reference_features.removed_pixel_counts,
        visibility_ratios=visibility,
        ratio_statuses=statuses,
        full_axis_boxes=full_boxes,
        reference_axis_boxes=reference_boxes,
        full_geometry_valid=full_valid,
        reference_geometry_valid=reference_valid,
        reference_fill_ratios=fill,
        reference_aspect_ratios=aspect,
        reference_angles=angles,
        reference_pose_statuses=pose_statuses,
        source_box_exists=source_exists,
    )


def execute_analysis(
    contract: InputContract,
    config: RunConfig,
) -> Tuple[FrameFeatures, ...]:
    tasks = contract.tasks
    results: List[FrameFeatures | None] = [None] * len(tasks)
    next_index = 0
    pending: Dict[Future[FrameFeatures], FrameTask] = {}
    reader_slots = BoundedSemaphore(config.execution.reader_threads)
    with ThreadPoolExecutor(
        max_workers=config.execution.workers,
        thread_name_prefix="postprocess-analysis",
    ) as pool:
        while next_index < len(tasks) or pending:
            while (
                next_index < len(tasks)
                and len(pending) < config.execution.max_in_flight
            ):
                task = tasks[next_index]
                pending[
                    pool.submit(process_frame, task, contract, config, reader_slots)
                ] = task
                next_index += 1
            done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
            for future in done:
                task = pending.pop(future)
                try:
                    result = future.result()
                except BaseException as exc:
                    for other in pending:
                        other.cancel()
                    raise RuntimeError(
                        f"frame {task.frame_id} analysis failed: "
                        f"{type(exc).__name__}: {exc}"
                    ) from exc
                results[result.ordinal] = result
    if any(item is None for item in results):
        raise RuntimeError("analysis completed with missing frame results")
    return tuple(item for item in results if item is not None)
