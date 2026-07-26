from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from typing import Dict, Iterator, Sequence, Tuple

from ..common.models import FrameTask
from ..common.output_writer import remove_yolo_frame, write_yolo_frame
from .frame_context import FrameArtifactStore, FrameContext
from .module_base import PipelineModule
from .orchestrator_config import ExecutionConfig


_WORKER_MODULES: Tuple[PipelineModule, ...] = ()
_WORKER_EXPECTED_DTYPE = ""
_WORKER_OVERWRITE = False
_WORKER_IMAGE_MODE = "hardlink_or_copy"


def init_worker(
    modules: Sequence[PipelineModule],
    expected_dtype: str,
    overwrite: bool,
    image_mode: str,
) -> None:
    global _WORKER_MODULES
    global _WORKER_EXPECTED_DTYPE
    global _WORKER_OVERWRITE
    global _WORKER_IMAGE_MODE
    _WORKER_MODULES = tuple(modules)
    _WORKER_EXPECTED_DTYPE = expected_dtype
    _WORKER_OVERWRITE = overwrite
    _WORKER_IMAGE_MODE = image_mode


def process_frame_task(task: FrameTask) -> Dict[str, object]:
    try:
        frame = FrameContext.load(task, _WORKER_EXPECTED_DTYPE)
    except Exception as exc:
        error = {
            "frame_id": task.frame_id,
            "module_id": "__frame__",
            "stage": "load_frame",
            "message": f"{type(exc).__name__}: {exc}",
            "rgb_path": str(task.rgb_path),
            "semantic_path": str(task.semantic_path),
        }
        return {
            "frame_id": task.frame_id,
            "status": "error",
            "modules": {},
            "errors": [error],
        }

    artifacts = FrameArtifactStore()
    computationally_ready = set()
    module_results: Dict[str, Dict[str, object]] = {}
    errors = []

    for module in _WORKER_MODULES:
        missing_dependencies = [
            dependency
            for dependency in module.depends_on
            if dependency not in computationally_ready
        ]
        if missing_dependencies:
            module_results[module.module_id] = {
                "status": "blocked",
                "boxes": 0,
                "reason": "upstream module failed: " + ", ".join(missing_dependencies),
            }
            continue

        try:
            result = module.process_frame(frame, artifacts)
            artifacts.publish(module.module_id, dict(result.artifacts))
            computationally_ready.add(module.module_id)
        except Exception as exc:
            error = {
                "frame_id": task.frame_id,
                "module_id": module.module_id,
                "stage": "process_frame",
                "message": f"{type(exc).__name__}: {exc}",
                "rgb_path": str(task.rgb_path),
                "semantic_path": str(task.semantic_path),
            }
            errors.append(error)
            module_results[module.module_id] = {
                "status": "error",
                "boxes": 0,
                "metrics": {},
            }
            continue

        boxes = (
            len(result.annotation.detections)
            if result.annotation is not None
            else 0
        )
        if result.disposition == "exclude":
            if _WORKER_OVERWRITE:
                remove_yolo_frame(
                    output_dir=module.output_dir,
                    task=task,
                    image_mode=_WORKER_IMAGE_MODE,
                )
            module_results[module.module_id] = {
                "status": "excluded",
                "boxes": boxes,
                "metrics": dict(result.metrics),
            }
            continue
        if result.annotation is None:
            module_results[module.module_id] = {
                "status": "success",
                "boxes": 0,
                "metrics": dict(result.metrics),
            }
            continue

        try:
            output_status = write_yolo_frame(
                output_dir=module.output_dir,
                task=task,
                annotation=result.annotation,
                image_width=frame.image_width,
                image_height=frame.image_height,
                class_names=module.class_names,
                overwrite=_WORKER_OVERWRITE,
                image_mode=_WORKER_IMAGE_MODE,
            )
            module_results[module.module_id] = {
                "status": output_status,
                "boxes": boxes,
                "metrics": dict(result.metrics),
            }
        except Exception as exc:
            error = {
                "frame_id": task.frame_id,
                "module_id": module.module_id,
                "stage": "write_output",
                "message": f"{type(exc).__name__}: {exc}",
                "rgb_path": str(task.rgb_path),
                "semantic_path": str(task.semantic_path),
            }
            errors.append(error)
            module_results[module.module_id] = {
                "status": "error",
                "boxes": 0,
                "metrics": dict(result.metrics),
            }

    has_blocked = any(
        result["status"] == "blocked" for result in module_results.values()
    )
    return {
        "frame_id": task.frame_id,
        "status": "error" if errors or has_blocked else "success",
        "modules": module_results,
        "errors": errors,
    }


def _worker_failure(task: FrameTask, exc: Exception) -> Dict[str, object]:
    return {
        "frame_id": task.frame_id,
        "status": "error",
        "modules": {},
        "errors": [
            {
                "frame_id": task.frame_id,
                "module_id": "__worker__",
                "stage": "worker",
                "message": f"{type(exc).__name__}: {exc}",
                "rgb_path": str(task.rgb_path),
                "semantic_path": str(task.semantic_path),
            }
        ],
    }


def execute_frame_tasks(
    tasks: Sequence[FrameTask],
    modules: Sequence[PipelineModule],
    expected_dtype: str,
    execution: ExecutionConfig,
    image_mode: str,
) -> Iterator[Dict[str, object]]:
    initargs = (
        tuple(modules),
        expected_dtype,
        execution.overwrite,
        image_mode,
    )
    if execution.workers == 1:
        init_worker(*initargs)
        for task in tasks:
            result = process_frame_task(task)
            yield result
            if execution.on_frame_error == "fail_fast" and result["status"] == "error":
                return
        return

    stop_submitting = False
    with ProcessPoolExecutor(
        max_workers=execution.workers,
        initializer=init_worker,
        initargs=initargs,
    ) as executor:
        pending: Dict[Future, FrameTask] = {}
        task_iterator = iter(tasks)

        def submit_until_full() -> None:
            if stop_submitting:
                return
            while len(pending) < execution.max_in_flight:
                try:
                    task = next(task_iterator)
                except StopIteration:
                    return
                pending[executor.submit(process_frame_task, task)] = task

        submit_until_full()
        while pending:
            done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
            for future in done:
                task = pending.pop(future)
                try:
                    result = future.result()
                except Exception as exc:
                    result = _worker_failure(task, exc)
                yield result
                if (
                    execution.on_frame_error == "fail_fast"
                    and result["status"] == "error"
                ):
                    stop_submitting = True
            submit_until_full()
