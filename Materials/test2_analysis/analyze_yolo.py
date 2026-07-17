from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def percentile_summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {key: None for key in ("min", "p25", "median", "mean", "p75", "max", "std")}
    array = np.asarray(values, dtype=np.float64)
    return {
        "min": float(np.min(array)),
        "p25": float(np.percentile(array, 25)),
        "median": float(np.median(array)),
        "mean": float(np.mean(array)),
        "p75": float(np.percentile(array, 75)),
        "max": float(np.max(array)),
        "std": float(np.std(array)),
    }


def frame_number(path: Path) -> int | None:
    match = re.search(r"(\d+)$", path.stem)
    return int(match.group(1)) if match else None


def intersection_over_union(a: dict, b: dict) -> float:
    left = max(a["x_min"], b["x_min"])
    top = max(a["y_min"], b["y_min"])
    right = min(a["x_max"], b["x_max"])
    bottom = min(a["y_max"], b["y_max"])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    if intersection == 0:
        return 0.0
    area_a = (a["x_max"] - a["x_min"]) * (a["y_max"] - a["y_min"])
    area_b = (b["x_max"] - b["x_min"]) * (b["y_max"] - b["y_min"])
    return intersection / (area_a + area_b - intersection)


def image_signature(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        gray = image.convert("L").resize((90, 160), Image.Resampling.BILINEAR)
        return np.asarray(gray, dtype=np.float32)


def adjacent_similarity(image_paths: list[Path]) -> list[dict]:
    signatures = {path.stem: image_signature(path) for path in image_paths}
    results = []
    for first, second in zip(image_paths, image_paths[1:]):
        a = signatures[first.stem].ravel()
        b = signatures[second.stem].ravel()
        mae = float(np.mean(np.abs(a - b)) / 255.0)
        if float(np.std(a)) == 0.0 or float(np.std(b)) == 0.0:
            correlation = 1.0 if np.array_equal(a, b) else 0.0
        else:
            correlation = float(np.corrcoef(a, b)[0, 1])
        first_number = frame_number(first)
        second_number = frame_number(second)
        results.append(
            {
                "first": first.name,
                "second": second.name,
                "frame_gap": (
                    second_number - first_number
                    if first_number is not None and second_number is not None
                    else None
                ),
                "downsampled_gray_mae": mae,
                "downsampled_gray_correlation": correlation,
            }
        )
    return results


def create_contact_sheet(
    image_paths: list[Path],
    objects_by_stem: dict[str, list[dict]],
    classes: list[str],
    destination: Path,
) -> None:
    columns = 5
    tile_width, tile_height = 360, 240
    rows = math.ceil(len(image_paths) / columns)
    sheet = Image.new("RGB", (columns * tile_width, rows * tile_height), (30, 30, 30))
    sheet_draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    colors = [(55, 220, 90), (255, 100, 70), (70, 160, 255), (245, 210, 70)]

    for index, path in enumerate(image_paths):
        objects = objects_by_stem.get(path.stem, [])
        with Image.open(path) as source:
            image = source.convert("RGB")
        draw = ImageDraw.Draw(image)
        for obj in objects:
            color = colors[obj["class_id"] % len(colors)]
            xy = (
                round(obj["x_min_px"]),
                round(obj["y_min_px"]),
                round(obj["x_max_px"]),
                round(obj["y_max_px"]),
            )
            draw.rectangle(xy, outline=color, width=4)

        if objects:
            x_min = max(0, int(min(item["x_min_px"] for item in objects) - 45))
            y_min = max(0, int(min(item["y_min_px"] for item in objects) - 70))
            x_max = min(image.width, int(max(item["x_max_px"] for item in objects) + 45))
            y_max = min(image.height, int(max(item["y_max_px"] for item in objects) + 70))
            crop = image.crop((x_min, y_min, x_max, y_max))
        else:
            crop = image

        crop.thumbnail((tile_width - 20, tile_height - 42), Image.Resampling.LANCZOS)
        tile_x = (index % columns) * tile_width
        tile_y = (index // columns) * tile_height
        paste_x = tile_x + (tile_width - crop.width) // 2
        paste_y = tile_y + 32 + (tile_height - 38 - crop.height) // 2
        sheet.paste(crop, (paste_x, paste_y))
        class_counts = Counter(obj["class_id"] for obj in objects)
        counts_text = ", ".join(
            f"{classes[class_id] if 0 <= class_id < len(classes) else class_id}:{count}"
            for class_id, count in sorted(class_counts.items())
        )
        sheet_draw.text((tile_x + 10, tile_y + 9), f"{path.name} | {counts_text}", fill=(240, 240, 240), font=font)

    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, quality=92)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a flat YOLO detection dataset.")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    dataset = args.dataset.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    classes_path = dataset / "classes.txt"
    classes = [line.strip() for line in classes_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    image_paths = sorted(
        (path for path in dataset.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS),
        key=lambda path: (frame_number(path) if frame_number(path) is not None else math.inf, path.name),
    )
    label_paths = sorted(
        (path for path in dataset.glob("*.txt") if path.name.lower() != "classes.txt"),
        key=lambda path: (frame_number(path) if frame_number(path) is not None else math.inf, path.name),
    )
    image_stems = {path.stem for path in image_paths}
    label_stems = {path.stem for path in label_paths}

    image_metadata = {}
    exact_image_hashes: dict[str, list[str]] = defaultdict(list)
    for path in image_paths:
        with Image.open(path) as image:
            width, height = image.size
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        exact_image_hashes[sha256].append(path.name)
        image_metadata[path.stem] = {"file": path.name, "width": width, "height": height, "sha256": sha256}

    issues: list[dict] = []
    objects: list[dict] = []
    objects_by_stem: dict[str, list[dict]] = defaultdict(list)
    empty_labels: list[str] = []

    for label_path in label_paths:
        lines = label_path.read_text(encoding="utf-8-sig").splitlines()
        nonempty_lines = [(line_number, line.strip()) for line_number, line in enumerate(lines, 1) if line.strip()]
        if not nonempty_lines:
            empty_labels.append(label_path.name)
        metadata = image_metadata.get(label_path.stem)
        for line_number, line in nonempty_lines:
            fields = line.split()
            if len(fields) != 5:
                issues.append({"file": label_path.name, "line": line_number, "type": "field_count", "value": line})
                continue
            try:
                raw_class, x_center, y_center, box_width, box_height = map(float, fields)
            except ValueError:
                issues.append({"file": label_path.name, "line": line_number, "type": "non_numeric", "value": line})
                continue
            class_id = int(raw_class)
            if raw_class != class_id:
                issues.append({"file": label_path.name, "line": line_number, "type": "non_integer_class", "value": raw_class})
            if not 0 <= class_id < len(classes):
                issues.append({"file": label_path.name, "line": line_number, "type": "class_out_of_range", "value": class_id})
            if not all(math.isfinite(value) for value in (x_center, y_center, box_width, box_height)):
                issues.append({"file": label_path.name, "line": line_number, "type": "non_finite_coordinate", "value": line})
                continue

            x_min = x_center - box_width / 2
            y_min = y_center - box_height / 2
            x_max = x_center + box_width / 2
            y_max = y_center + box_height / 2
            if box_width <= 0 or box_height <= 0:
                issues.append({"file": label_path.name, "line": line_number, "type": "non_positive_size", "value": [box_width, box_height]})
            if not (0 <= x_center <= 1 and 0 <= y_center <= 1 and 0 < box_width <= 1 and 0 < box_height <= 1):
                issues.append({"file": label_path.name, "line": line_number, "type": "normalized_value_out_of_range", "value": [x_center, y_center, box_width, box_height]})
            if x_min < 0 or y_min < 0 or x_max > 1 or y_max > 1:
                issues.append({"file": label_path.name, "line": line_number, "type": "box_crosses_image_boundary", "value": [x_min, y_min, x_max, y_max]})

            width_px = metadata["width"] if metadata else None
            height_px = metadata["height"] if metadata else None
            width_pixels = box_width * width_px if width_px else None
            height_pixels = box_height * height_px if height_px else None
            obj = {
                "image": metadata["file"] if metadata else None,
                "label": label_path.name,
                "line": line_number,
                "frame": frame_number(label_path),
                "class_id": class_id,
                "class_name": classes[class_id] if 0 <= class_id < len(classes) else None,
                "x_center": x_center,
                "y_center": y_center,
                "width": box_width,
                "height": box_height,
                "area_fraction": box_width * box_height,
                "aspect_ratio": width_pixels / height_pixels if height_pixels else None,
                "normalized_width_height_ratio": box_width / box_height if box_height else None,
                "x_min": x_min,
                "y_min": y_min,
                "x_max": x_max,
                "y_max": y_max,
                "x_center_px": x_center * width_px if width_px else None,
                "y_center_px": y_center * height_px if height_px else None,
                "width_px": width_pixels,
                "height_px": height_pixels,
                "x_min_px": x_min * width_px if width_px else None,
                "y_min_px": y_min * height_px if height_px else None,
                "x_max_px": x_max * width_px if width_px else None,
                "y_max_px": y_max * height_px if height_px else None,
            }
            objects.append(obj)
            objects_by_stem[label_path.stem].append(obj)

    duplicate_box_entries = []
    max_iou_by_image = {}
    for stem, image_objects in objects_by_stem.items():
        fingerprints = Counter(
            (obj["class_id"], obj["x_center"], obj["y_center"], obj["width"], obj["height"])
            for obj in image_objects
        )
        for fingerprint, count in fingerprints.items():
            if count > 1:
                duplicate_box_entries.append({"label": f"{stem}.txt", "box": fingerprint, "count": count})
        max_iou = 0.0
        for first_index, first in enumerate(image_objects):
            for second in image_objects[first_index + 1 :]:
                max_iou = max(max_iou, intersection_over_union(first, second))
        max_iou_by_image[stem] = max_iou

    class_counts = Counter(obj["class_id"] for obj in objects)
    objects_per_image = [len(objects_by_stem.get(path.stem, [])) for path in image_paths]
    similarities = adjacent_similarity(image_paths)
    same_sequence_similarities = [item for item in similarities if item["frame_gap"] == 15]

    statistics = {
        "width_normalized": percentile_summary([obj["width"] for obj in objects]),
        "height_normalized": percentile_summary([obj["height"] for obj in objects]),
        "area_fraction": percentile_summary([obj["area_fraction"] for obj in objects]),
        "aspect_ratio": percentile_summary([obj["aspect_ratio"] for obj in objects]),
        "width_pixels": percentile_summary([obj["width_px"] for obj in objects if obj["width_px"] is not None]),
        "height_pixels": percentile_summary([obj["height_px"] for obj in objects if obj["height_px"] is not None]),
        "x_center": percentile_summary([obj["x_center"] for obj in objects]),
        "y_center": percentile_summary([obj["y_center"] for obj in objects]),
        "objects_per_image": percentile_summary(objects_per_image),
        "max_pairwise_iou_per_image": percentile_summary(list(max_iou_by_image.values())),
        "adjacent_frame_gap_15_mae": percentile_summary(
            [item["downsampled_gray_mae"] for item in same_sequence_similarities]
        ),
        "adjacent_frame_gap_15_correlation": percentile_summary(
            [item["downsampled_gray_correlation"] for item in same_sequence_similarities]
        ),
    }

    smallest = sorted(objects, key=lambda item: item["area_fraction"])[:5]
    largest = sorted(objects, key=lambda item: item["area_fraction"], reverse=True)[:5]
    dimensions = Counter((item["width"], item["height"]) for item in image_metadata.values())
    exact_duplicate_groups = [names for names in exact_image_hashes.values() if len(names) > 1]

    per_frame = []
    for path in image_paths:
        frame_objects = sorted(objects_by_stem.get(path.stem, []), key=lambda item: item["x_center"])
        per_frame.append(
            {
                "image": path.name,
                "frame": frame_number(path),
                "objects": len(frame_objects),
                "class_counts": dict(Counter(obj["class_name"] for obj in frame_objects)),
                "mean_width_px": float(np.mean([obj["width_px"] for obj in frame_objects])) if frame_objects else None,
                "mean_height_px": float(np.mean([obj["height_px"] for obj in frame_objects])) if frame_objects else None,
                "mean_area_fraction": float(np.mean([obj["area_fraction"] for obj in frame_objects])) if frame_objects else None,
                "mean_y_center": float(np.mean([obj["y_center"] for obj in frame_objects])) if frame_objects else None,
                "sorted_x_centers": [obj["x_center"] for obj in frame_objects],
            }
        )

    summary = {
        "dataset": str(dataset),
        "classes": classes,
        "counts": {
            "images": len(image_paths),
            "label_files": len(label_paths),
            "objects": len(objects),
            "empty_labels": len(empty_labels),
            "format_or_range_issues": len(issues),
            "duplicate_box_entries": len(duplicate_box_entries),
            "exact_duplicate_image_groups": len(exact_duplicate_groups),
        },
        "class_distribution": [
            {"class_id": class_id, "class_name": class_name, "objects": class_counts.get(class_id, 0)}
            for class_id, class_name in enumerate(classes)
        ],
        "pairing": {
            "images_without_labels": sorted(image_stems - label_stems),
            "labels_without_images": sorted(label_stems - image_stems),
        },
        "image_dimensions": [
            {"width": width, "height": height, "images": count}
            for (width, height), count in sorted(dimensions.items())
        ],
        "empty_labels": empty_labels,
        "issues": issues,
        "duplicate_box_entries": duplicate_box_entries,
        "exact_duplicate_image_groups": exact_duplicate_groups,
        "statistics": statistics,
        "smallest_boxes": smallest,
        "largest_boxes": largest,
        "adjacent_similarity": similarities,
        "per_frame": per_frame,
    }

    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    with (output / "objects.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(objects[0].keys()) if objects else [])
        writer.writeheader()
        writer.writerows(objects)
    with (output / "per_frame.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        fieldnames = ["image", "frame", "objects", "tooth", "lack", "mean_width_px", "mean_height_px", "mean_area_fraction", "mean_y_center"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in per_frame:
            writer.writerow(
                {
                    "image": item["image"],
                    "frame": item["frame"],
                    "objects": item["objects"],
                    "tooth": item["class_counts"].get("tooth", 0),
                    "lack": item["class_counts"].get("lack", 0),
                    "mean_width_px": item["mean_width_px"],
                    "mean_height_px": item["mean_height_px"],
                    "mean_area_fraction": item["mean_area_fraction"],
                    "mean_y_center": item["mean_y_center"],
                }
            )
    create_contact_sheet(image_paths, objects_by_stem, classes, output / "annotated_contact_sheet.jpg")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
