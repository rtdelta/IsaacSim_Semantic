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
from typing import Dict, Iterator, Optional, Sequence, Tuple

import numpy as np
from PIL import Image


if os.name == "nt":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


SEMANTIC_PREFIX = "semantic_id_"
RGB_PREFIX = "rgb_"
RGB_SUFFIX = ".png"
TOOTH_PREFIX = "tooth_"

_TOOTH_IDS: Tuple[int, ...] = ()
_MIN_PIXELS = 10
_OVERWRITE = False
_EXPECTED_DTYPE = ""


@dataclass(frozen=True)
class FrameTask:
    frame_id: str
    semantic_path: str
    rgb_path: str
    output_dir: str


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是正整数")
    return parsed


def parse_args() -> argparse.Namespace:
    default_workers = min(os.cpu_count() or 1, 8)
    parser = argparse.ArgumentParser(
        description="将 Isaac Sim 语义 ID 图批量转换为单类 tooth YOLO 标注。"
    )
    parser.add_argument("--input", required=True, type=Path, help="包含 RGB、NPY 和 mapping 的输入目录")
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


def load_mapping(mapping_path: Path) -> Tuple[Tuple[int, ...], str]:
    with mapping_path.open("r", encoding="utf-8-sig") as handle:
        mapping = json.load(handle)

    classes = mapping.get("classes")
    if not isinstance(classes, list):
        raise ValueError("semantic_mapping.json 缺少 classes 数组")

    tooth_ids = []
    for item in classes:
        label = str(item.get("label", ""))
        if label.startswith(TOOTH_PREFIX):
            tooth_ids.append(int(item["id"]))

    tooth_ids = sorted(set(tooth_ids))
    if not tooth_ids:
        raise ValueError("mapping 中没有找到 label 以 tooth_ 开头的语义类别")

    expected_dtype = str(mapping.get("dataset_dtype", ""))
    return tuple(tooth_ids), expected_dtype


def iter_frame_candidates(input_dir: Path, output_dir: Path) -> Iterator[Tuple[Optional[FrameTask], Optional[Dict[str, str]]]]:
    with os.scandir(input_dir) as entries:
        for entry in entries:
            if not entry.is_file() or not entry.name.startswith(SEMANTIC_PREFIX) or not entry.name.endswith(".npy"):
                continue

            frame_id = entry.name[len(SEMANTIC_PREFIX) : -len(".npy")]
            semantic_path = Path(entry.path)
            if not frame_id:
                yield None, {
                    "frame_id": "",
                    "semantic_path": str(semantic_path),
                    "rgb_path": "",
                    "message": "语义文件名中缺少帧编号",
                }
                continue

            rgb_path = input_dir / f"{RGB_PREFIX}{frame_id}{RGB_SUFFIX}"
            if not rgb_path.is_file():
                yield None, {
                    "frame_id": frame_id,
                    "semantic_path": str(semantic_path),
                    "rgb_path": str(rgb_path),
                    "message": "缺少对应 RGB 文件",
                }
                continue

            yield (
                FrameTask(
                    frame_id=frame_id,
                    semantic_path=str(semantic_path),
                    rgb_path=str(rgb_path),
                    output_dir=str(output_dir),
                ),
                None,
            )


def init_worker(tooth_ids: Sequence[int], min_pixels: int, overwrite: bool, expected_dtype: str) -> None:
    global _TOOTH_IDS, _MIN_PIXELS, _OVERWRITE, _EXPECTED_DTYPE
    _TOOTH_IDS = tuple(tooth_ids)
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

        target_mask = np.isin(semantic, _TOOTH_IDS, assume_unique=True)
        all_y, all_x = np.nonzero(target_mask)
        semantic_ids = np.asarray(semantic[all_y, all_x]) if all_x.size else np.empty(0, dtype=semantic.dtype)

        lines = []
        small_masks = 0
        for semantic_id in _TOOTH_IDS:
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
                raise ValueError(f"semantic id {semantic_id} 产生非有限坐标")
            if not (0.0 <= x_center <= 1.0 and 0.0 <= y_center <= 1.0):
                raise ValueError(f"semantic id {semantic_id} 的中心点越界")
            if not (0.0 < normalized_width <= 1.0 and 0.0 < normalized_height <= 1.0):
                raise ValueError(f"semantic id {semantic_id} 的框尺寸越界")

            lines.append(
                f"0 {x_center:.8f} {y_center:.8f} {normalized_width:.8f} {normalized_height:.8f}"
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
    input_dir = args.input.resolve()
    output_dir = args.output.resolve()
    max_in_flight = args.max_in_flight or args.workers * 2
    if max_in_flight < args.workers:
        raise ValueError("--max-in-flight 不能小于 --workers")
    if not input_dir.is_dir():
        raise FileNotFoundError(f"输入目录不存在：{input_dir}")
    if input_dir == output_dir:
        raise ValueError("输入目录和输出目录不能相同")

    mapping_path = input_dir / "semantic_mapping.json"
    if not mapping_path.is_file():
        raise FileNotFoundError(f"缺少 mapping 文件：{mapping_path}")

    tooth_ids, expected_dtype = load_mapping(mapping_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(output_dir / "classes.txt", "tooth\n")

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
            initargs=(tooth_ids, args.min_pixels, args.overwrite, expected_dtype),
        ) as executor:
            pending: Dict[Future, FrameTask] = {}

            for task, discovery_error in iter_frame_candidates(input_dir, output_dir):
                stats["discovered"] += 1
                if discovery_error is not None:
                    stats["failed"] += 1
                    write_error(error_handle, {"status": "error", **discovery_error})
                    continue

                assert task is not None
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

    if stats["discovered"] == 0:
        stats["failed"] += 1
        with errors_temporary.open("a", encoding="utf-8", newline="\n") as error_handle:
            write_error(
                error_handle,
                {"status": "error", "message": f"输入目录中没有 {SEMANTIC_PREFIX}*.npy 文件"},
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
    print(f"生成 tooth 框：{stats['boxes']}")
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
