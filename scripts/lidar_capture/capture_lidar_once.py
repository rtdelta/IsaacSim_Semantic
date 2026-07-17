"""Capture one ROS 2 PointCloud2 message and export it as PLY/CSV/JSON.

This script is intended for Isaac Sim RTX LiDAR data published through the
ROS 2 bridge, but it works with any PointCloud2 topic that contains x/y/z
fields.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
import struct
import sys
import time
from typing import Any

import rclpy
from rclpy.qos import DurabilityPolicy
from rclpy.qos import HistoryPolicy
from rclpy.qos import QoSProfile
from rclpy.qos import ReliabilityPolicy
from sensor_msgs.msg import PointCloud2
from sensor_msgs.msg import PointField


FIELD_FORMATS = {
    PointField.INT8: "b",
    PointField.UINT8: "B",
    PointField.INT16: "h",
    PointField.UINT16: "H",
    PointField.INT32: "i",
    PointField.UINT32: "I",
    PointField.FLOAT32: "f",
    PointField.FLOAT64: "d",
}


def default_output_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "isaacProject" / "lidar_exports"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture one PointCloud2 frame from Isaac Sim/ROS 2 and export it."
    )
    parser.add_argument("--topic", default="/point_cloud", help="PointCloud2 topic name.")
    parser.add_argument(
        "--output-dir",
        default=str(default_output_dir()),
        help="Directory for exported PLY, CSV, and summary JSON files.",
    )
    parser.add_argument(
        "--prefix",
        default="point_cloud",
        help="Output filename prefix before the timestamp.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=30.0,
        help="Seconds to wait for a PointCloud2 message.",
    )
    parser.add_argument(
        "--csv-limit",
        type=int,
        default=5000,
        help="Number of valid points to write to CSV. Use 0 to skip CSV export.",
    )
    parser.add_argument(
        "--max-points",
        type=int,
        default=0,
        help="Maximum valid points to write to PLY. Use 0 to export all valid points.",
    )
    parser.add_argument(
        "--best-effort",
        action="store_true",
        help="Use best-effort subscriber QoS instead of reliable.",
    )
    return parser.parse_args()


def unpack_field_value(msg: PointCloud2, field: PointField, base_offset: int) -> Any:
    fmt = FIELD_FORMATS.get(field.datatype)
    if fmt is None:
        return None
    endian = ">" if msg.is_bigendian else "<"
    return struct.unpack_from(endian + fmt, msg.data, base_offset + field.offset)[0]


def extract_xyz(msg: PointCloud2, max_points: int) -> list[tuple[float, float, float]]:
    fields = {field.name: field for field in msg.fields}
    missing = [name for name in ("x", "y", "z") if name not in fields]
    if missing:
        available = [field.name for field in msg.fields]
        raise RuntimeError(f"Missing fields {missing}; available fields: {available}")

    total_points = msg.width * msg.height
    valid_points: list[tuple[float, float, float]] = []
    stop_after = total_points if max_points <= 0 else min(total_points, max_points)

    for index in range(total_points):
        base_offset = index * msg.point_step
        x = unpack_field_value(msg, fields["x"], base_offset)
        y = unpack_field_value(msg, fields["y"], base_offset)
        z = unpack_field_value(msg, fields["z"], base_offset)
        if x is None or y is None or z is None:
            continue
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
            continue
        valid_points.append((float(x), float(y), float(z)))
        if len(valid_points) >= stop_after:
            break

    return valid_points


def write_csv(path: Path, points: list[tuple[float, float, float]], limit: int) -> None:
    if limit <= 0:
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["x", "y", "z"])
        writer.writerows(points[:limit])


def write_ascii_ply(path: Path, points: list[tuple[float, float, float]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        file.write("ply\n")
        file.write("format ascii 1.0\n")
        file.write(f"element vertex {len(points)}\n")
        file.write("property float x\n")
        file.write("property float y\n")
        file.write("property float z\n")
        file.write("end_header\n")
        for x, y, z in points:
            file.write(f"{x:.6f} {y:.6f} {z:.6f}\n")


def summarize_message(
    msg: PointCloud2,
    points: list[tuple[float, float, float]],
    topic: str,
    csv_path: Path | None,
    ply_path: Path,
    summary_path: Path,
    truncated: bool,
) -> dict[str, Any]:
    return {
        "topic": topic,
        "frame_id": msg.header.frame_id,
        "stamp_sec": msg.header.stamp.sec,
        "stamp_nanosec": msg.header.stamp.nanosec,
        "width": msg.width,
        "height": msg.height,
        "point_step": msg.point_step,
        "row_step": msg.row_step,
        "raw_data_length": len(msg.data),
        "fields": [
            {
                "name": field.name,
                "offset": field.offset,
                "datatype": field.datatype,
                "count": field.count,
            }
            for field in msg.fields
        ],
        "exported_valid_points": len(points),
        "truncated_by_max_points": truncated,
        "csv_path": str(csv_path) if csv_path else None,
        "ply_path": str(ply_path),
        "summary_path": str(summary_path),
    }


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    suffix = "_FULL" if args.max_points <= 0 else f"_MAX{args.max_points}"
    ply_path = output_dir / f"{args.prefix}_{timestamp}{suffix}.ply"
    csv_path = output_dir / f"{args.prefix}_{timestamp}_first{args.csv_limit}.csv"
    summary_path = output_dir / f"{args.prefix}_{timestamp}_summary.json"

    state: dict[str, Any] = {"done": False, "summary": None, "error": None}

    rclpy.init()
    node = rclpy.create_node("pointcloud_export_once")
    qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=10)
    qos.reliability = (
        ReliabilityPolicy.BEST_EFFORT if args.best_effort else ReliabilityPolicy.RELIABLE
    )
    qos.durability = DurabilityPolicy.VOLATILE

    def on_message(msg: PointCloud2) -> None:
        if state["done"]:
            return
        try:
            points = extract_xyz(msg, args.max_points)
            truncated = args.max_points > 0 and (msg.width * msg.height) > len(points)
            write_ascii_ply(ply_path, points)
            actual_csv_path = csv_path if args.csv_limit > 0 else None
            if actual_csv_path:
                write_csv(actual_csv_path, points, args.csv_limit)
            summary = summarize_message(
                msg,
                points,
                args.topic,
                actual_csv_path,
                ply_path,
                summary_path,
                truncated,
            )
            with summary_path.open("w", encoding="utf-8") as file:
                json.dump(summary, file, indent=2)
            state["summary"] = summary
        except Exception as exc:  # noqa: BLE001 - keep CLI failures readable.
            state["error"] = repr(exc)
        finally:
            state["done"] = True

    node.create_subscription(PointCloud2, args.topic, on_message, qos)

    deadline = time.time() + args.timeout_sec
    while rclpy.ok() and not state["done"] and time.time() < deadline:
        rclpy.spin_once(node, timeout_sec=0.2)

    node.destroy_node()
    rclpy.shutdown()

    if state["summary"]:
        print(json.dumps(state["summary"], indent=2))
        return 0
    if state["error"]:
        print(json.dumps({"error": state["error"]}, indent=2), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "error": f"Timeout waiting for {args.topic}",
                "hint": "Open the stage in Isaac Sim, click Play, and verify the ROS 2 graph topic name.",
            },
            indent=2,
        ),
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
