#!/usr/bin/env python3
"""Migrate Fangshan Joint rotation lines into the current source-asset frame once.

This command is deliberately separate from the normal build pipeline.  It reads
the historical USD only to recover its four world-space Joint rotation lines,
maps those lines back through the historical visual transforms, proves that the
resulting numeric frame is shared by the current Mesh and PLY inputs, and writes
an independent calibration file for all future builds.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path


PART_IDS = ["track", "cab", "boom", "arm", "bucket_without_teeth"] + [
    f"tooth_{number:02d}_{side}"
    for number in range(1, 6)
    for side in ("front", "back")
]

PART_TO_REFERENCE_GAUSSIAN = {
    "track": "/excavator_prim/track_prim/track_3DGS",
    "cab": "/excavator_prim/cab_prim/cab_3DGS",
    "boom": "/excavator_prim/boom_prim/boom_3DGS",
    "arm": "/excavator_prim/arm_prim/arm_3DGS",
    "bucket_without_teeth": "/excavator_prim/bucket_with_teeth_prim/bucket_without_teeth_3DGS",
    **{
        f"tooth_{number:02d}_{side}": (
            f"/excavator_prim/bucket_with_teeth_prim/tooth_{number:02d}_{side}_3DGS"
        )
        for number in range(1, 6)
        for side in ("front", "back")
    },
}

JOINT_SPECS = {
    "track_cab_joint": {
        "reference_joint": "/excavator_prim/Joints/track_operator_cab_joint",
        "body0_link": "track",
        "body1_link": "cab",
        "body0_mesh": "track_mesh",
        "body1_mesh": "cab_mesh",
    },
    "cab_boom_joint": {
        "reference_joint": "/excavator_prim/Joints/platform_boom_joint",
        "body0_link": "cab",
        "body1_link": "boom",
        "body0_mesh": "cab_mesh",
        "body1_mesh": "boom_mesh",
    },
    "boom_arm_joint": {
        "reference_joint": "/excavator_prim/Joints/boom_small_arm_joint",
        "body0_link": "boom",
        "body1_link": "arm",
        "body0_mesh": "boom_mesh",
        "body1_mesh": "arm_mesh",
    },
    "arm_bucket_joint": {
        "reference_joint": "/excavator_prim/Joints/small_arm_bucket_joint",
        "body0_link": "arm",
        "body1_link": "bucket",
        "body0_mesh": "arm_mesh",
        "body1_mesh": "bucket_mesh",
    },
}

REFERENCE_MESH_BY_LINK = {
    "track": "/excavator_prim/track_prim/track_mesh",
    "cab": "/excavator_prim/cab_prim/cab_mesh",
    "boom": "/excavator_prim/boom_prim/boom_mesh",
    "arm": "/excavator_prim/arm_prim/arm_mesh",
    "bucket": "/excavator_prim/bucket_with_teeth_prim/bucket_with_teeth_mesh",
}


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_hash(path: Path, expected: str | None, label: str) -> str:
    actual = _sha256(path)
    if expected and actual.lower() != expected.lower():
        raise RuntimeError(f"{label} SHA-256 mismatch: expected {expected}, got {actual}")
    return actual


def _vec(value):
    return [float(value[index]) for index in range(len(value))]


def _matrix(value):
    if isinstance(value, tuple):
        value = value[0]
    return [[float(value[row][column]) for column in range(4)] for row in range(4)]


def _sorted_rows(values):
    import numpy as np

    order = np.lexsort((values[:, 2], values[:, 1], values[:, 0]))
    return values[order]


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


def _line_metrics(points, center, axis):
    import numpy as np

    offsets = points - center
    axial = offsets @ axis
    radial = np.linalg.norm(offsets - np.outer(axial, axis), axis=1)
    quantiles = np.quantile(radial, [0.0, 0.001, 0.01, 0.05, 0.5])
    center_distance = np.linalg.norm(offsets, axis=1)
    return {
        "point_count": int(len(points)),
        "radial_distance_to_axis_m": {
            "minimum": float(quantiles[0]),
            "q001": float(quantiles[1]),
            "q01": float(quantiles[2]),
            "q05": float(quantiles[3]),
            "median": float(quantiles[4]),
        },
        "minimum_vertex_distance_to_center_m": float(center_distance.min()),
        "axial_extent_about_center_m": [float(axial.min()), float(axial.max())],
    }


def _reference_mesh_points(stage):
    import numpy as np
    from pxr import UsdGeom

    result = {}
    for link_id, path in REFERENCE_MESH_BY_LINK.items():
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsA(UsdGeom.Mesh):
            raise RuntimeError(f"historical validation Mesh not found: {path}")
        result[link_id] = np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get(), dtype=np.float32)
    return result


def _current_mesh_points(path: Path, prim_path: str):
    import numpy as np
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(str(path), load=Usd.Stage.LoadNone)
    if stage is None:
        raise RuntimeError(f"failed to open current Mesh USD: {path}")
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsA(UsdGeom.Mesh):
        raise RuntimeError(f"current Mesh Prim not found: {prim_path}")
    return np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get(), dtype=np.float32)


def _exact_component_assignment(path: Path, prim_path: str, historical_meshes, mesh_hash: str):
    """Freeze component ownership while the historical five-Link Mesh is available."""
    import numpy as np
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(str(path), load=Usd.Stage.LoadNone)
    mesh = UsdGeom.Mesh(stage.GetPrimAtPath(prim_path))
    points = np.asarray(mesh.GetPointsAttr().Get(), dtype=np.float32)
    counts = np.asarray(mesh.GetFaceVertexCountsAttr().Get(), dtype=np.int64)
    indices = np.asarray(mesh.GetFaceVertexIndicesAttr().Get(), dtype=np.int64)
    if not np.all(counts == 3):
        raise RuntimeError("exact component assignment requires triangular faces")
    triangles = indices.reshape(-1, 3)
    parent = np.arange(len(points), dtype=np.int64)

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left, right):
        left_root, right_root = find(int(left)), find(int(right))
        if left_root != right_root:
            parent[right_root] = left_root

    for first, second, third in triangles:
        union(first, second)
        union(first, third)
    roots = np.fromiter((find(index) for index in range(len(points))), dtype=np.int64)
    face_roots = roots[triangles[:, 0]]
    components = [np.flatnonzero(face_roots == root) for root in np.unique(face_roots)]

    owner_by_point = {}
    for link_id, link_points in historical_meshes.items():
        for point in np.asarray(link_points, dtype=np.float32):
            owner_by_point.setdefault(point.tobytes(), set()).add(link_id)
    mesh_part_by_link = {
        "track": "track_mesh",
        "cab": "cab_mesh",
        "boom": "boom_mesh",
        "arm": "arm_mesh",
        "bucket": "bucket_mesh",
    }
    assignments = []
    for component_index, face_rows in enumerate(components):
        vertex_indices = np.unique(triangles[face_rows].reshape(-1))
        candidates = set(historical_meshes)
        for vertex_index in vertex_indices:
            candidates.intersection_update(
                owner_by_point.get(points[vertex_index].tobytes(), set())
            )
        if len(candidates) != 1:
            raise RuntimeError(
                f"component {component_index} has no unique exact historical owner: "
                f"{sorted(candidates)}"
            )
        link_id = next(iter(candidates))
        assignments.append(
            {
                "component_index": component_index,
                "face_count": int(len(face_rows)),
                "vertex_count": int(len(vertex_indices)),
                "mesh_part_id": mesh_part_by_link[link_id],
                "historical_link_id": link_id,
            }
        )
    return {
        "schema_version": "1.0",
        "kind": "exact_mesh_component_assignment",
        "one_time_migration_artifact": True,
        "normal_build_dependency": True,
        "source": {
            "file_sha256": mesh_hash,
            "prim_path": prim_path,
            "point_count": int(len(points)),
            "face_count": int(len(triangles)),
        },
        "component_count": len(assignments),
        "assignments": assignments,
    }


def _verify_ply_numeric_frame(stage, ply_dir: Path):
    import numpy as np
    import usd_convert_gsplat as gsplat

    source_arrays = []
    historical_arrays = []
    parts = []
    for part_id in PART_IDS:
        source_path = ply_dir / f"{part_id}.ply"
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        source = gsplat.read_ply(str(source_path)).positions.astype(np.float64)
        prim_path = PART_TO_REFERENCE_GAUSSIAN[part_id]
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.GetAttribute("positions"):
            raise RuntimeError(f"historical Gaussian positions not found: {prim_path}")
        historical = np.asarray(prim.GetAttribute("positions").Get(), dtype=np.float64)
        if source.shape != historical.shape:
            raise RuntimeError(
                f"Gaussian point count mismatch for {part_id}: {source.shape} != {historical.shape}"
            )
        rotation, translation, errors = _fit_rigid(source, historical)
        parts.append(
            {
                "part_id": part_id,
                "point_count": int(len(source)),
                "maximum_error_m": float(errors.max()),
                "rms_error_m": float(np.sqrt(np.mean(errors * errors))),
            }
        )
        source_arrays.append(source)
        historical_arrays.append(historical)

    source_all = np.concatenate(source_arrays)
    historical_all = np.concatenate(historical_arrays)
    rotation, translation, errors = _fit_rigid(source_all, historical_all)
    maximum_error = float(errors.max())
    rms_error = float(np.sqrt(np.mean(errors * errors)))
    if maximum_error > 1.0e-9:
        raise RuntimeError(
            f"current PLY and historical Gaussian numeric frames differ by {maximum_error} m"
        )
    return {
        "passed": True,
        "mapping_convention": "historical_position = current_ply_position @ row_rotation + translation",
        "point_count": int(len(source_all)),
        "row_rotation": rotation.tolist(),
        "translation": translation.tolist(),
        "determinant": float(np.linalg.det(rotation)),
        "maximum_error_m": maximum_error,
        "rms_error_m": rms_error,
        "parts": parts,
    }


def _joint_source_frame(stage, cache, joint_path: str, reference_mesh_points):
    import numpy as np
    from pxr import Gf, UsdGeom

    prim = stage.GetPrimAtPath(joint_path)
    if not prim or prim.GetTypeName() != "PhysicsRevoluteJoint":
        raise RuntimeError(f"historical RevoluteJoint not found: {joint_path}")
    body0_targets = prim.GetRelationship("physics:body0").GetTargets()
    body1_targets = prim.GetRelationship("physics:body1").GetTargets()
    if len(body0_targets) != 1 or len(body1_targets) != 1:
        raise RuntimeError(f"historical Joint must have exactly two bodies: {joint_path}")

    axis_token = str(prim.GetAttribute("physics:axis").Get())
    unit_axis = {
        "X": Gf.Vec3d(1, 0, 0),
        "Y": Gf.Vec3d(0, 1, 0),
        "Z": Gf.Vec3d(0, 0, 1),
    }.get(axis_token)
    if unit_axis is None:
        raise RuntimeError(f"unsupported historical Joint axis {axis_token!r}: {joint_path}")

    side_records = []
    for side, body_path in enumerate((body0_targets[0], body1_targets[0])):
        body = stage.GetPrimAtPath(body_path)
        local_pos = prim.GetAttribute(f"physics:localPos{side}").Get()
        local_rot = prim.GetAttribute(f"physics:localRot{side}").Get()
        body_world = cache.GetLocalToWorldTransform(body)
        center_world = body_world.Transform(Gf.Vec3d(*local_pos))
        axis_body = Gf.Rotation(local_rot).TransformDir(unit_axis)
        axis_world = body_world.TransformDir(axis_body).GetNormalized()

        mesh_prims = [child for child in body.GetAllChildren() if child.IsA(UsdGeom.Mesh)]
        if len(mesh_prims) != 1:
            raise RuntimeError(
                f"expected one historical visual Mesh directly under {body_path}, found {len(mesh_prims)}"
            )
        visual_world = cache.GetLocalToWorldTransform(mesh_prims[0])
        world_to_source = visual_world.GetInverse()
        center_source = world_to_source.Transform(center_world)
        axis_source = world_to_source.TransformDir(axis_world).GetNormalized()
        side_records.append(
            {
                "body_path": str(body_path),
                "mesh_path": str(mesh_prims[0].GetPath()),
                "local_pos": _vec(local_pos),
                "local_rot": str(local_rot),
                "body_world_matrix": _matrix(body_world),
                "visual_world_matrix": _matrix(visual_world),
                "center_world": _vec(center_world),
                "axis_world": _vec(axis_world),
                "center_source": _vec(center_source),
                "axis_source": _vec(axis_source),
            }
        )

    center0 = np.asarray(side_records[0]["center_source"], dtype=np.float64)
    center1 = np.asarray(side_records[1]["center_source"], dtype=np.float64)
    axis0 = np.asarray(side_records[0]["axis_source"], dtype=np.float64)
    axis1 = np.asarray(side_records[1]["axis_source"], dtype=np.float64)
    if float(axis0 @ axis1) < 0.0:
        axis1 = -axis1
    center = 0.5 * (center0 + center1)
    axis = axis0 + axis1
    axis /= np.linalg.norm(axis)
    center_error = float(np.linalg.norm(center0 - center1))
    alignment = float(np.clip(axis0 @ axis1, -1.0, 1.0))
    angle_error = float(math.degrees(math.acos(alignment)))
    if center_error > 1.0e-5 or angle_error > 1.0e-4:
        raise RuntimeError(
            f"historical Joint sides disagree after visual inverse for {joint_path}: "
            f"center={center_error} m, angle={angle_error} deg"
        )
    return center, axis, side_records, center_error, alignment, angle_error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-usd", required=True, type=Path)
    parser.add_argument("--combined-mesh", required=True, type=Path)
    parser.add_argument("--combined-mesh-prim", default="/World/mesh_")
    parser.add_argument("--ply-dir", required=True, type=Path)
    parser.add_argument("--calibration-template", required=True, type=Path)
    parser.add_argument("--output-calibration", required=True, type=Path)
    parser.add_argument("--output-report", required=True, type=Path)
    parser.add_argument("--output-mesh-assignment", required=True, type=Path)
    parser.add_argument("--expected-reference-sha256")
    parser.add_argument("--expected-mesh-sha256")
    args = parser.parse_args()

    import numpy as np
    from pxr import Usd, UsdGeom

    reference_usd = args.reference_usd.expanduser().resolve()
    combined_mesh = args.combined_mesh.expanduser().resolve()
    ply_dir = args.ply_dir.expanduser().resolve()
    template_path = args.calibration_template.expanduser().resolve()
    for path in (reference_usd, combined_mesh, template_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    if not ply_dir.is_dir():
        raise NotADirectoryError(ply_dir)
    reference_hash = _require_hash(
        reference_usd, args.expected_reference_sha256, "historical USD"
    )
    mesh_hash = _require_hash(combined_mesh, args.expected_mesh_sha256, "current Mesh")

    stage = Usd.Stage.Open(str(reference_usd), load=Usd.Stage.LoadAll)
    if stage is None:
        raise RuntimeError(f"failed to open historical USD: {reference_usd}")
    cache = UsdGeom.XformCache(Usd.TimeCode.Default())

    historical_meshes = _reference_mesh_points(stage)
    historical_all = np.concatenate(list(historical_meshes.values()), axis=0)
    current_mesh = _current_mesh_points(combined_mesh, args.combined_mesh_prim)
    mesh_equal = False
    max_mesh_difference = None
    if historical_all.shape == current_mesh.shape:
        difference = np.abs(_sorted_rows(historical_all) - _sorted_rows(current_mesh))
        max_mesh_difference = float(difference.max())
        mesh_equal = bool(np.array_equal(_sorted_rows(historical_all), _sorted_rows(current_mesh)))
    if not mesh_equal:
        raise RuntimeError(
            "current combined Mesh is not the exact numeric-vertex union of the five historical Link Meshes"
        )

    mesh_assignment = _exact_component_assignment(
        combined_mesh, args.combined_mesh_prim, historical_meshes, mesh_hash
    )

    ply_alignment = _verify_ply_numeric_frame(stage, ply_dir)
    calibration = copy.deepcopy(_read_json(template_path))
    calibration["schema_version"] = "1.1"
    calibration["source"] = {
        "mesh_source_id": "combined_mesh",
        "source_file": str(args.combined_mesh),
        "source_prim_path": args.combined_mesh_prim,
        "source_file_sha256": mesh_hash,
    }
    calibration["coordinate_frame"] = {
        "name": "source_mesh_numeric_frame",
        "units_to_meters": 1.0,
        "up_axis": str(UsdGeom.GetStageUpAxis(Usd.Stage.Open(str(combined_mesh)))),
        "object_to_source_matrix": np.eye(4).tolist(),
    }
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    calibration["migration"] = {
        "one_time_operation": True,
        "status": "completed",
        "normal_build_dependency": False,
        "performed_at_utc": timestamp,
        "tool": "migrate_fangshan_joint_frames.py",
        "historical_source": {
            "file": str(args.reference_usd),
            "sha256": reference_hash,
            "role": "one-time recovery of Joint world rotation lines and motion conventions",
        },
        "retirement_rule": (
            "After this calibration is reviewed and stored, normal builds read this file and must not "
            "open or fall back to the historical USD."
        ),
    }

    template_joints = {item["id"]: item for item in calibration.get("joints", [])}
    output_joints = []
    report_joints = []
    for joint_id, spec in JOINT_SPECS.items():
        if joint_id not in template_joints:
            raise RuntimeError(f"calibration template is missing {joint_id}")
        center, axis, sides, center_error, alignment, angle_error = _joint_source_frame(
            stage, cache, spec["reference_joint"], historical_meshes
        )
        line_metrics = {
            spec["body0_mesh"]: _line_metrics(
                historical_meshes[spec["body0_link"]], center, axis
            ),
            spec["body1_mesh"]: _line_metrics(
                historical_meshes[spec["body1_link"]], center, axis
            ),
        }
        entry = copy.deepcopy(template_joints[joint_id])
        entry["method"] = "reference_joint_migration_v1"
        entry["center"] = center.tolist()
        entry["axis"] = axis.tolist()
        entry["axis_is_normalized"] = True
        entry["selection"]["source_mesh_part_ids"] = [
            spec["body0_mesh"],
            spec["body1_mesh"],
        ]
        entry["selection"]["selected_vertex_indices"] = []
        entry["selection"]["selected_vertex_indices_file"] = None
        entry["fit"] = {key: None for key in entry.get("fit", {})}
        entry["validation"] = {
            "status": "passed",
            "method": "dual_body_visual_inverse_plus_exact_current_mesh_identity",
            "body_center_disagreement_m": center_error,
            "body_axis_alignment_dot": alignment,
            "body_axis_angle_error_deg": angle_error,
            "mesh_line_proximity_metrics": line_metrics,
            "interpretation": (
                "Proximity values are audit diagnostics, not a separately fitted replacement axis."
            ),
        }
        entry["provenance"] = {
            "tool": "migrate_fangshan_joint_frames.py",
            "operator": None,
            "timestamp_utc": timestamp,
            "reference_joint_path": spec["reference_joint"],
            "reference_usd_sha256": reference_hash,
            "notes": (
                "One-time migration. The historical localPos/localRot values were used only to recover "
                "the world rotation line; they were not copied into the new model."
            ),
        }
        output_joints.append(entry)
        report_joints.append(
            {
                "joint_id": joint_id,
                "reference_joint_path": spec["reference_joint"],
                "body_links": [spec["body0_link"], spec["body1_link"]],
                "center_source_mesh_numeric_frame": center.tolist(),
                "axis_source_mesh_numeric_frame": axis.tolist(),
                "body_center_disagreement_m": center_error,
                "body_axis_alignment_dot": alignment,
                "body_axis_angle_error_deg": angle_error,
                "historical_side_evidence": sides,
                "mesh_line_proximity_metrics": line_metrics,
            }
        )
    calibration["joints"] = output_joints

    report = {
        "schema_version": "1.0",
        "kind": "fangshan_one_time_joint_migration_report",
        "status": "passed",
        "one_time_operation": True,
        "normal_build_dependency": False,
        "performed_at_utc": timestamp,
        "inputs": {
            "historical_usd": {"path": str(reference_usd), "sha256": reference_hash},
            "current_combined_mesh": {"path": str(combined_mesh), "sha256": mesh_hash},
            "current_ply_directory": str(ply_dir),
        },
        "frame_proofs": {
            "current_mesh_equals_historical_five_mesh_vertex_multiset": {
                "passed": mesh_equal,
                "point_count": int(len(current_mesh)),
                "maximum_sorted_point_difference_m": max_mesh_difference,
            },
            "current_ply_equals_historical_gaussian_numeric_frame": ply_alignment,
        },
        "mesh_component_assignment": {
            "path": str(args.output_mesh_assignment),
            "component_count": mesh_assignment["component_count"],
            "method": "exact historical Link vertex ownership",
        },
        "joints": report_joints,
        "output_calibration": str(args.output_calibration),
        "retirement_rule": (
            "The historical USD is forbidden as an implicit or explicit normal-build input after "
            "the generated calibration has been accepted."
        ),
    }
    _write_json(args.output_calibration, calibration)
    _write_json(args.output_mesh_assignment, mesh_assignment)
    _write_json(args.output_report, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "output_calibration": str(args.output_calibration),
                "output_report": str(args.output_report),
                "joint_count": len(output_joints),
                "mesh_identity": mesh_equal,
                "ply_max_error_m": ply_alignment["maximum_error_m"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
