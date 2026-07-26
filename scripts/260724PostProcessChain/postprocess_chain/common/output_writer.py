from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Mapping, Tuple

from .models import FrameTask, YoloAnnotationSet
from .yolo_format import format_annotation_set


def atomic_write_text(destination: Path, text: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.name}.{os.getpid()}.tmp")
    try:
        temporary.unlink(missing_ok=True)
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_json(destination: Path, value: Mapping[str, Any]) -> None:
    atomic_write_text(
        destination,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def materialize_image(source: Path, output_dir: Path, image_mode: str) -> None:
    if image_mode == "none":
        return
    destination = output_dir / source.name
    if destination.exists():
        return

    temporary = destination.with_name(f"{destination.name}.{os.getpid()}.tmp")
    temporary.unlink(missing_ok=True)
    try:
        if image_mode == "copy":
            shutil.copy2(source, temporary)
        elif image_mode == "hardlink_or_copy":
            try:
                os.link(source, temporary)
            except OSError:
                shutil.copy2(source, temporary)
        else:
            raise ValueError(f"unsupported image_mode: {image_mode}")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_yolo_output(output_dir: Path, class_names: Tuple[str, ...]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    classes_text = "".join(f"{name}\n" for name in class_names)
    atomic_write_text(output_dir / "classes.txt", classes_text)


def remove_yolo_frame(output_dir: Path, task: FrameTask, image_mode: str) -> None:
    (output_dir / f"{task.rgb_path.stem}.txt").unlink(missing_ok=True)
    if image_mode != "none":
        (output_dir / task.rgb_path.name).unlink(missing_ok=True)


def write_yolo_frame(
    output_dir: Path,
    task: FrameTask,
    annotation: YoloAnnotationSet,
    image_width: int,
    image_height: int,
    class_names: Tuple[str, ...],
    overwrite: bool,
    image_mode: str,
) -> str:
    label_path = output_dir / f"{task.rgb_path.stem}.txt"
    if label_path.exists() and not overwrite:
        materialize_image(task.rgb_path, output_dir, image_mode)
        return "skipped"

    label_text = format_annotation_set(
        annotation,
        image_width,
        image_height,
        class_names,
    )
    materialize_image(task.rgb_path, output_dir, image_mode)
    atomic_write_text(label_path, label_text)
    return "written"
