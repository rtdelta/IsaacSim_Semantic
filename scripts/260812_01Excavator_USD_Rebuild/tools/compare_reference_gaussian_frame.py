#!/usr/bin/env python3
"""Fit the coordinate transform between source PLY and reference USD 3DGS."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PART_IDS = ["track", "cab", "boom", "arm", "bucket_without_teeth"] + [
    f"tooth_{number:02d}_{side}"
    for number in range(1, 6)
    for side in ("front", "back")
]


def _part_from_prim_name(name: str):
    suffix = "_3DGS"
    if not name.endswith(suffix):
        return None
    candidate = name[: -len(suffix)]
    return candidate if candidate in PART_IDS else None


def _fit_rigid(source, target):
    import numpy as np

    source_mean = source.mean(axis=0)
    target_mean = target.mean(axis=0)
    source_centered = source - source_mean
    target_centered = target - target_mean
    u, _, vt = np.linalg.svd(source_centered.T @ target_centered)
    row_rotation = u @ vt
    if np.linalg.det(row_rotation) < 0.0:
        u[:, -1] *= -1.0
        row_rotation = u @ vt
    translation = target_mean - source_mean @ row_rotation
    predicted = source @ row_rotation + translation
    errors = np.linalg.norm(predicted - target, axis=1)
    return row_rotation, translation, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-usd", required=True, type=Path)
    parser.add_argument("--ply-dir", required=True, type=Path)
    parser.add_argument("--joint-frames", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    import numpy as np
    import usd_convert_gsplat as gsplat
    from pxr import Usd

    stage = Usd.Stage.Open(str(args.reference_usd.expanduser().resolve()), load=Usd.Stage.LoadAll)
    if stage is None:
        raise RuntimeError(f"failed to open {args.reference_usd}")

    reference_prims = {}
    for prim in stage.TraverseAll():
        part_id = _part_from_prim_name(prim.GetName())
        if part_id and prim.GetAttribute("positions"):
            reference_prims[part_id] = prim

    missing = sorted(set(PART_IDS) - set(reference_prims))
    if missing:
        raise RuntimeError(f"reference Gaussian prims not found for {missing}")

    source_arrays = []
    target_arrays = []
    parts = []
    for part_id in PART_IDS:
        source = gsplat.read_ply(str(args.ply_dir / f"{part_id}.ply")).positions.astype(np.float64)
        target = np.asarray(reference_prims[part_id].GetAttribute("positions").Get(), dtype=np.float64)
        if source.shape != target.shape:
            raise RuntimeError(f"point count mismatch for {part_id}: {source.shape} != {target.shape}")
        row_rotation, translation, errors = _fit_rigid(source, target)
        parts.append(
            {
                "part_id": part_id,
                "point_count": int(source.shape[0]),
                "reference_prim_path": str(reference_prims[part_id].GetPath()),
                "fit_max_error_m": float(errors.max()),
                "fit_rms_error_m": float(np.sqrt(np.mean(errors * errors))),
            }
        )
        source_arrays.append(source)
        target_arrays.append(target)

    source_all = np.concatenate(source_arrays, axis=0)
    target_all = np.concatenate(target_arrays, axis=0)
    row_rotation, translation, errors = _fit_rigid(source_all, target_all)

    frames = json.loads(args.joint_frames.read_text(encoding="utf-8"))
    source_joint_frames = []
    for joint in frames["joints"]:
        center_reference = np.asarray(joint["center0_world"], dtype=np.float64)
        axis_reference = np.asarray(joint["axis0_world"], dtype=np.float64)
        center_source = (center_reference - translation) @ row_rotation.T
        axis_source = axis_reference @ row_rotation.T
        axis_source /= np.linalg.norm(axis_source)
        source_joint_frames.append(
            {
                "reference_joint_path": joint["path"],
                "center_reference_frame": center_reference.tolist(),
                "axis_reference_frame": axis_reference.tolist(),
                "center_source_ply_frame": center_source.tolist(),
                "axis_source_ply_frame": axis_source.tolist(),
            }
        )

    report = {
        "schema_version": "1.0",
        "kind": "reference_gaussian_frame_alignment",
        "mapping_convention": "reference_position = source_position @ row_rotation + translation",
        "point_count": int(source_all.shape[0]),
        "row_rotation": row_rotation.tolist(),
        "column_rotation_old_to_reference": row_rotation.T.tolist(),
        "translation": translation.tolist(),
        "determinant": float(np.linalg.det(row_rotation)),
        "max_error_m": float(errors.max()),
        "rms_error_m": float(np.sqrt(np.mean(errors * errors))),
        "parts": parts,
        "joint_frames_in_source_ply_coordinates": source_joint_frames,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
