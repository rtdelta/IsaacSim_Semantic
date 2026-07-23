from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import shutil
import sys
import time
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Sequence, Tuple

import numpy as np
from PIL import Image


if os.name == "nt":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


SEMANTIC_PREFIX = "semantic_id_"
RGB_PREFIX = "rgb_"
RGB_SUFFIX = ".png"

_TARGET_CLASSES: Tuple["ResolvedYoloClass", ...] = ()
_MIN_PIXELS = 10
_OVERWRITE = False
_EXPECTED_DTYPE = ""


@dataclass(frozen=True)
class FrameTask:
    frame_id: str
    semantic_path: str
    rgb_path: str
    output_dir: str


@dataclass(frozen=True)
class ResolvedYoloClass:
    yolo_id: int
    yolo_name: str
    semantic_labels: Tuple[str, ...]
    semantic_ids: Tuple[int, ...]


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是正整数")
    return parsed


def parse_args() -> argparse.Namespace:
    default_workers = min(os.cpu_count() or 1, 8)
    parser = argparse.ArgumentParser(
        description="根据类别配置将 Isaac Sim 语义 ID 图批量转换为 YOLO 检测标注。"
    )
    parser.add_argument("--rgb-dir", required=True, type=Path, help="包含 rgb_<帧号>.png 的目录")
    parser.add_argument(
        "--semantic-dir",
        required=True,
        type=Path,
        help="包含 semantic_id_<帧号>.npy 的目录",
    )
    parser.add_argument("--mapping", required=True, type=Path, help="semantic_mapping.json 文件路径")
    parser.add_argument(
        "--class-config",
        required=True,
        type=Path,
        help="定义 YOLO 类别及对应语义标签的 JSON 文件路径",
    )
    parser.add_argument("--output", required=True, type=Path, help="YOLO 图片和标签输出目录")
    parser.add_argument("--workers", type=positive_int, default=default_workers, help="并行进程数")
    parser.add_argument(
        "--max-in-flight",
        type=positive_int,
        default=None,
        help="最多同时等待的任务数，默认是 workers 的 2 倍",
    )
    parser.add_argument("--min-pixels", type=positive_int, default=10, help="生成框所需的最少语义像素数")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的 TXT 标签")
    return parser.parse_args()


def load_mapping(mapping_path: Path) -> Tuple[Dict[str, int], str]:
    with mapping_path.open("r", encoding="utf-8-sig") as handle:
        mapping = json.load(handle)

    if not isinstance(mapping, dict):
        raise ValueError("semantic mapping 的顶层必须是 JSON 对象")

    classes = mapping.get("classes")
    if not isinstance(classes, list):
        raise ValueError("semantic_mapping.json 缺少 classes 数组")

    label_to_id: Dict[str, int] = {}
    id_to_label: Dict[int, str] = {}
    for index, item in enumerate(classes):
        if not isinstance(item, dict):
            raise ValueError(f"mapping classes[{index}] 必须是 JSON 对象")

        label = item.get("label")
        semantic_id = item.get("id")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"mapping classes[{index}].label 必须是非空字符串")
        label = label.strip()
        if isinstance(semantic_id, bool) or not isinstance(semantic_id, int):
            raise ValueError(f"mapping 中标签 {label!r} 的 id 必须是整数")
        if label in label_to_id:
            raise ValueError(f"mapping 中存在重复标签：{label}")
        if semantic_id in id_to_label:
            raise ValueError(
                f"mapping 中 semantic id {semantic_id} 同时分配给 {id_to_label[semantic_id]!r} 和 {label!r}"
            )
        label_to_id[label] = semantic_id
        id_to_label[semantic_id] = label

    if not label_to_id:
        raise ValueError("semantic_mapping.json 的 classes 不能为空")

    expected_dtype = str(mapping.get("dataset_dtype", ""))
    if expected_dtype:
        try:
            np.dtype(expected_dtype)
        except TypeError as exc:
            raise ValueError(f"mapping 中的 dataset_dtype 无效：{expected_dtype}") from exc
    return label_to_id, expected_dtype


def load_class_config(
    config_path: Path,
    label_to_id: Dict[str, int],
) -> Tuple[ResolvedYoloClass, ...]:
    with config_path.open("r", encoding="utf-8-sig") as handle:
        config = json.load(handle)

    if not isinstance(config, dict):
        raise ValueError("YOLO 类别配置的顶层必须是 JSON 对象")
    if config.get("schema_version") != 1:
        raise ValueError("YOLO 类别配置 schema_version 必须为 1")

    raw_targets = config.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("YOLO 类别配置必须包含非空 targets 数组")

    targets_by_id: Dict[int, ResolvedYoloClass] = {}
    used_names = set()
    used_semantic_labels: Dict[str, int] = {}

    for index, raw_target in enumerate(raw_targets):
        if not isinstance(raw_target, dict):
            raise ValueError(f"targets[{index}] 必须是 JSON 对象")

        yolo_id = raw_target.get("yolo_id")
        yolo_name = raw_target.get("yolo_name")
        semantic_labels = raw_target.get("semantic_labels")

        if isinstance(yolo_id, bool) or not isinstance(yolo_id, int) or yolo_id < 0:
            raise ValueError(f"targets[{index}].yolo_id 必须是非负整数")
        if yolo_id in targets_by_id:
            raise ValueError(f"YOLO 类别配置中存在重复 yolo_id：{yolo_id}")
        if not isinstance(yolo_name, str) or not yolo_name.strip():
            raise ValueError(f"targets[{index}].yolo_name 必须是非空字符串")
        yolo_name = yolo_name.strip()
        if yolo_name in used_names:
            raise ValueError(f"YOLO 类别配置中存在重复 yolo_name：{yolo_name}")
        if not isinstance(semantic_labels, list) or not semantic_labels:
            raise ValueError(f"targets[{index}].semantic_labels 必须是非空数组")

        normalized_labels = []
        semantic_ids = []
        for label_index, label in enumerate(semantic_labels):
            if not isinstance(label, str) or not label.strip():
                raise ValueError(
                    f"targets[{index}].semantic_labels[{label_index}] 必须是非空字符串"
                )
            label = label.strip()
            if label in used_semantic_labels:
                previous_id = used_semantic_labels[label]
                raise ValueError(
                    f"语义标签 {label!r} 同时分配给 YOLO 类别 {previous_id} 和 {yolo_id}"
                )
            if label not in label_to_id:
                raise ValueError(f"YOLO 类别配置中的语义标签不在 mapping 中：{label}")

            used_semantic_labels[label] = yolo_id
            normalized_labels.append(label)
            semantic_ids.append(label_to_id[label])

        used_names.add(yolo_name)
        targets_by_id[yolo_id] = ResolvedYoloClass(
            yolo_id=yolo_id,
            yolo_name=yolo_name,
            semantic_labels=tuple(normalized_labels),
            semantic_ids=tuple(semantic_ids),
        )

    expected_ids = list(range(len(raw_targets)))
    actual_ids = sorted(targets_by_id)
    if actual_ids != expected_ids:
        raise ValueError(
            f"yolo_id 必须从 0 开始连续编号；期望 {expected_ids}，实际 {actual_ids}"
        )

    return tuple(targets_by_id[yolo_id] for yolo_id in expected_ids)


def _summarize_frame_ids(frame_ids: Sequence[str], limit: int = 10) -> str:
    visible = ", ".join(frame_ids[:limit])
    remaining = len(frame_ids) - limit
    return f"{visible}（另有 {remaining} 个）" if remaining > 0 else visible


def discover_frame_tasks(
    rgb_dir: Path,
    semantic_dir: Path,
    output_dir: Path,
) -> Tuple[FrameTask, ...]:
    semantic_by_frame: Dict[str, Path] = {}
    with os.scandir(semantic_dir) as entries:
        for entry in entries:
            if not entry.is_file() or not entry.name.startswith(SEMANTIC_PREFIX) or not entry.name.endswith(".npy"):
                continue

            frame_id = entry.name[len(SEMANTIC_PREFIX) : -len(".npy")]
            if not frame_id:
                raise ValueError(f"语义文件名中缺少帧编号：{entry.name}")
            semantic_by_frame[frame_id] = Path(entry.path)

    if not semantic_by_frame:
        raise FileNotFoundError(f"semantic 目录中没有 {SEMANTIC_PREFIX}*.npy 文件：{semantic_dir}")

    rgb_by_frame: Dict[str, Path] = {}
    with os.scandir(rgb_dir) as entries:
        for entry in entries:
            if not entry.is_file() or not entry.name.startswith(RGB_PREFIX) or not entry.name.endswith(RGB_SUFFIX):
                continue

            frame_id = entry.name[len(RGB_PREFIX) : -len(RGB_SUFFIX)]
            if not frame_id:
                raise ValueError(f"RGB 文件名中缺少帧编号：{entry.name}")
            rgb_by_frame[frame_id] = Path(entry.path)

    missing_rgb = sorted(set(semantic_by_frame) - set(rgb_by_frame))
    missing_semantic = sorted(set(rgb_by_frame) - set(semantic_by_frame))
    mismatch_messages = []
    if missing_rgb:
        mismatch_messages.append(f"缺少 RGB 的帧：{_summarize_frame_ids(missing_rgb)}")
    if missing_semantic:
        mismatch_messages.append(f"缺少 semantic NPY 的帧：{_summarize_frame_ids(missing_semantic)}")
    if mismatch_messages:
        raise ValueError("RGB 与 semantic 帧不匹配；" + "；".join(mismatch_messages))

    return tuple(
        FrameTask(
            frame_id=frame_id,
            semantic_path=str(semantic_by_frame[frame_id]),
            rgb_path=str(rgb_by_frame[frame_id]),
            output_dir=str(output_dir),
        )
        for frame_id in sorted(semantic_by_frame)
    )


def init_worker(
    target_classes: Sequence[ResolvedYoloClass],
    min_pixels: int,
    overwrite: bool,
    expected_dtype: str,
) -> None:
    global _TARGET_CLASSES, _MIN_PIXELS, _OVERWRITE, _EXPECTED_DTYPE
    _TARGET_CLASSES = tuple(target_classes)
    _MIN_PIXELS = min_pixels
    _OVERWRITE = overwrite
    _EXPECTED_DTYPE = expected_dtype


def atomic_write_text(destination: Path, text: str) -> None:
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


def materialize_image(source: Path, output_dir: Path) -> None:
    destination = output_dir / source.name
    if destination.exists():
        return

    temporary = destination.with_name(f"{destination.name}.{os.getpid()}.tmp")
    temporary.unlink(missing_ok=True)
    try:
        try:
            os.link(source, temporary)
        except OSError:
            shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def process_frame(task: FrameTask) -> Dict[str, object]:
    semantic_path = Path(task.semantic_path)
    rgb_path = Path(task.rgb_path)
    output_dir = Path(task.output_dir)
    label_path = output_dir / f"{rgb_path.stem}.txt"

    try:
        if label_path.exists() and not _OVERWRITE:
            materialize_image(rgb_path, output_dir)
            return {
                "status": "skipped",
                "frame_id": task.frame_id,
                "boxes": 0,
                "empty": False,
                "small_masks": 0,
            }

        semantic = np.load(semantic_path, mmap_mode="r", allow_pickle=False)
        if semantic.ndim != 2:
            raise ValueError(f"语义数组必须是二维，实际 shape={semantic.shape}")
        if _EXPECTED_DTYPE and str(semantic.dtype) != _EXPECTED_DTYPE:
            raise ValueError(f"语义数组 dtype={semantic.dtype}，mapping 声明为 {_EXPECTED_DTYPE}")

        with Image.open(rgb_path) as image:
            image_width, image_height = image.size
        if semantic.shape != (image_height, image_width):
            raise ValueError(
                f"尺寸不一致：NPY shape={semantic.shape}，RGB size=({image_width}, {image_height})"
            )

        target_semantic_ids = tuple(
            semantic_id
            for target_class in _TARGET_CLASSES
            for semantic_id in target_class.semantic_ids
        )
        target_mask = np.isin(semantic, target_semantic_ids)
        all_y, all_x = np.nonzero(target_mask)
        semantic_ids = np.asarray(semantic[all_y, all_x]) if all_x.size else np.empty(0, dtype=semantic.dtype)

        lines = []
        small_masks = 0
        for target_class in _TARGET_CLASSES:
            for semantic_label, semantic_id in zip(
                target_class.semantic_labels,
                target_class.semantic_ids,
            ):
                selected = semantic_ids == semantic_id
                pixel_count = int(np.count_nonzero(selected))
                if pixel_count == 0:
                    continue
                if pixel_count < _MIN_PIXELS:
                    small_masks += 1
                    continue

                x_values = all_x[selected]
                y_values = all_y[selected]
                left = int(x_values.min())
                right = int(x_values.max()) + 1
                top = int(y_values.min())
                bottom = int(y_values.max()) + 1

                box_width = right - left
                box_height = bottom - top
                x_center = (left + right) / 2.0 / image_width
                y_center = (top + bottom) / 2.0 / image_height
                normalized_width = box_width / image_width
                normalized_height = box_height / image_height

                values = (x_center, y_center, normalized_width, normalized_height)
                if not all(np.isfinite(value) for value in values):
                    raise ValueError(
                        f"语义标签 {semantic_label!r}（id={semantic_id}）产生非有限坐标"
                    )
                if not (0.0 <= x_center <= 1.0 and 0.0 <= y_center <= 1.0):
                    raise ValueError(f"语义标签 {semantic_label!r}（id={semantic_id}）的中心点越界")
                if not (0.0 < normalized_width <= 1.0 and 0.0 < normalized_height <= 1.0):
                    raise ValueError(f"语义标签 {semantic_label!r}（id={semantic_id}）的框尺寸越界")

                lines.append(
                    f"{target_class.yolo_id} {x_center:.8f} {y_center:.8f} "
                    f"{normalized_width:.8f} {normalized_height:.8f}"
                )

        materialize_image(rgb_path, output_dir)
        atomic_write_text(label_path, "\n".join(lines) + ("\n" if lines else ""))
        return {
            "status": "success",
            "frame_id": task.frame_id,
            "boxes": len(lines),
            "empty": not lines,
            "small_masks": small_masks,
        }
    except Exception as exc:
        return {
            "status": "error",
            "frame_id": task.frame_id,
            "semantic_path": str(semantic_path),
            "rgb_path": str(rgb_path),
            "message": f"{type(exc).__name__}: {exc}",
            "boxes": 0,
            "empty": False,
            "small_masks": 0,
        }


def write_error(handle, error: Dict[str, object]) -> None:
    handle.write(json.dumps(error, ensure_ascii=False) + "\n")
    handle.flush()


def main() -> int:
    args = parse_args()
    rgb_dir = args.rgb_dir.resolve()
    semantic_dir = args.semantic_dir.resolve()
    mapping_path = args.mapping.resolve()
    class_config_path = args.class_config.resolve()
    output_dir = args.output.resolve()
    max_in_flight = args.max_in_flight or args.workers * 2
    if max_in_flight < args.workers:
        raise ValueError("--max-in-flight 不能小于 --workers")
    if not rgb_dir.is_dir():
        raise FileNotFoundError(f"RGB 目录不存在：{rgb_dir}")
    if not semantic_dir.is_dir():
        raise FileNotFoundError(f"semantic 目录不存在：{semantic_dir}")
    if not mapping_path.is_file():
        raise FileNotFoundError(f"缺少 mapping 文件：{mapping_path}")
    if not class_config_path.is_file():
        raise FileNotFoundError(f"缺少 YOLO 类别配置文件：{class_config_path}")
    for input_dir, description in ((rgb_dir, "RGB"), (semantic_dir, "semantic")):
        if (
            output_dir == input_dir
            or input_dir in output_dir.parents
            or output_dir in input_dir.parents
        ):
            raise ValueError(f"输出目录不能与 {description} 目录相同或互相包含")

    label_to_id, expected_dtype = load_mapping(mapping_path)
    target_classes = load_class_config(class_config_path, label_to_id)
    frame_tasks = discover_frame_tasks(rgb_dir, semantic_dir, output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    classes_text = "".join(f"{target.yolo_name}\n" for target in target_classes)
    atomic_write_text(output_dir / "classes.txt", classes_text)

    print(f"RGB 目录：{rgb_dir}")
    print(f"semantic 目录：{semantic_dir}")
    print(f"mapping：{mapping_path}")
    print(f"YOLO 类别配置：{class_config_path}")
    print(f"已配对帧数：{len(frame_tasks)}")
    for target in target_classes:
        labels = ", ".join(target.semantic_labels)
        print(f"YOLO {target.yolo_id} {target.yolo_name} <- {labels}")

    errors_path = output_dir / "errors.jsonl"
    errors_temporary = output_dir / "errors.jsonl.tmp"
    errors_path.unlink(missing_ok=True)
    errors_temporary.unlink(missing_ok=True)

    stats = {
        "discovered": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
        "empty": 0,
        "boxes": 0,
        "small_masks": 0,
    }
    started = time.perf_counter()

    def consume_result(result: Dict[str, object], error_handle) -> None:
        status = str(result["status"])
        if status == "success":
            stats["success"] += 1
            stats["boxes"] += int(result["boxes"])
            stats["empty"] += int(bool(result["empty"]))
            stats["small_masks"] += int(result["small_masks"])
        elif status == "skipped":
            stats["skipped"] += 1
        else:
            stats["failed"] += 1
            write_error(error_handle, result)

        completed = stats["success"] + stats["failed"] + stats["skipped"]
        if completed and completed % 100 == 0:
            print(
                f"已完成 {completed} 帧：成功 {stats['success']}，跳过 {stats['skipped']}，失败 {stats['failed']}"
            )

    with errors_temporary.open("w", encoding="utf-8", newline="\n") as error_handle:
        with ProcessPoolExecutor(
            max_workers=args.workers,
            initializer=init_worker,
            initargs=(target_classes, args.min_pixels, args.overwrite, expected_dtype),
        ) as executor:
            pending: Dict[Future, FrameTask] = {}

            for task in frame_tasks:
                stats["discovered"] += 1
                pending[executor.submit(process_frame, task)] = task
                if len(pending) < max_in_flight:
                    continue

                done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
                for future in done:
                    finished_task = pending.pop(future)
                    try:
                        consume_result(future.result(), error_handle)
                    except Exception as exc:
                        consume_result(
                            {
                                "status": "error",
                                "frame_id": finished_task.frame_id,
                                "semantic_path": finished_task.semantic_path,
                                "rgb_path": finished_task.rgb_path,
                                "message": f"WorkerFailure: {type(exc).__name__}: {exc}",
                            },
                            error_handle,
                        )

            while pending:
                done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
                for future in done:
                    finished_task = pending.pop(future)
                    try:
                        consume_result(future.result(), error_handle)
                    except Exception as exc:
                        consume_result(
                            {
                                "status": "error",
                                "frame_id": finished_task.frame_id,
                                "semantic_path": finished_task.semantic_path,
                                "rgb_path": finished_task.rgb_path,
                                "message": f"WorkerFailure: {type(exc).__name__}: {exc}",
                            },
                            error_handle,
                        )

    if stats["failed"]:
        os.replace(errors_temporary, errors_path)
    else:
        errors_temporary.unlink(missing_ok=True)

    elapsed = time.perf_counter() - started
    completed = stats["success"] + stats["failed"] + stats["skipped"]
    frame_rate = completed / elapsed if elapsed else 0.0
    print("\n转换完成")
    print(f"发现帧数：{stats['discovered']}")
    print(f"成功帧数：{stats['success']}")
    print(f"跳过帧数：{stats['skipped']}")
    print(f"失败帧数：{stats['failed']}")
    print(f"空标签帧数：{stats['empty']}")
    print(f"生成 YOLO 框：{stats['boxes']}")
    print(f"跳过小掩码：{stats['small_masks']}")
    print(f"处理耗时：{elapsed:.2f} 秒")
    print(f"平均速度：{frame_rate:.2f} 帧/秒")
    if stats["failed"]:
        print(f"错误详情：{errors_path}")
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n用户中断。已完成的标签仍然有效，可直接重新运行继续处理。", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f"错误：{type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)
