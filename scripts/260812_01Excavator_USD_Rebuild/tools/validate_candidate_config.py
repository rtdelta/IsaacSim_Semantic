#!/usr/bin/env python3
"""Perform static validation of an excavator candidate build configuration."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve_path(value: str, config_dir: Path, expand_environment_variables: bool) -> Path:
    if expand_environment_variables:
        value = os.path.expandvars(value)
    path = Path(value).expanduser()
    return path if path.is_absolute() else (config_dir / path).resolve()


def _unique_index(items, collection, errors):
    result = {}
    for index, item in enumerate(items):
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            errors.append(f"{collection}[{index}] has no non-empty id")
        elif item_id in result:
            errors.append(f"duplicate {collection} id: {item_id}")
        else:
            result[item_id] = item
    return result


def _full_prim_path(root, relative):
    if relative.startswith("/"):
        return relative
    return root.rstrip("/") + "/" + relative.strip("/")


def _finite_vector(value, length):
    return (
        isinstance(value, list)
        and len(value) == length
        and all(isinstance(item, (int, float)) and math.isfinite(item) for item in value)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()

    config_path = args.config.expanduser().resolve()
    report_path = args.report.expanduser().resolve()
    config = _read_json(config_path)
    config_dir = config_path.parent
    errors = []
    warnings = []
    blockers = []
    checks = {}

    if config.get("schema_version") != "1.0":
        errors.append(f"unsupported schema_version: {config.get('schema_version')!r}")

    root_path = config.get("stage", {}).get("root_prim_path")
    if not isinstance(root_path, str) or not root_path.startswith("/") or root_path == "/":
        errors.append("stage.root_prim_path must be an absolute non-root Prim path")

    links = _unique_index(config.get("links", []), "links", errors)
    gaussians = _unique_index(config.get("gaussian", {}).get("parts", []), "gaussian.parts", errors)
    mesh_sources = _unique_index(config.get("mesh", {}).get("sources", []), "mesh.sources", errors)
    mesh_parts = _unique_index(config.get("mesh", {}).get("parts", []), "mesh.parts", errors)
    joints = _unique_index(config.get("joints", []), "joints", errors)

    prim_paths = {}
    for collection_name, items, path_field in (
        ("links", links, "prim_path"),
        ("gaussian.parts", gaussians, "relative_prim_path"),
        ("mesh.parts", mesh_parts, "relative_prim_path"),
        ("joints", joints, "prim_path"),
    ):
        for item_id, item in items.items():
            value = item.get(path_field)
            if not isinstance(value, str) or not value:
                errors.append(f"{collection_name}.{item_id}.{path_field} is empty")
                continue
            full_path = _full_prim_path(root_path or "", value)
            if full_path in prim_paths:
                errors.append(
                    f"duplicate resolved Prim path {full_path}: {prim_paths[full_path]} and {collection_name}.{item_id}"
                )
            else:
                prim_paths[full_path] = f"{collection_name}.{item_id}"

    expand_env = bool(config.get("paths", {}).get("expand_environment_variables", True))
    input_files = []
    for part_id, part in gaussians.items():
        if part.get("link_id") not in links:
            errors.append(f"gaussian part {part_id} references missing link {part.get('link_id')!r}")
        source_file = part.get("source_file")
        if not isinstance(source_file, str) or not source_file:
            errors.append(f"gaussian part {part_id} has no source_file")
        else:
            input_files.append((f"gaussian.parts.{part_id}", _resolve_path(source_file, config_dir, expand_env)))

    for source_id, source in mesh_sources.items():
        source_file = source.get("source_file")
        if not isinstance(source_file, str) or not source_file:
            errors.append(f"mesh source {source_id} has no source_file")
        else:
            input_files.append((f"mesh.sources.{source_id}", _resolve_path(source_file, config_dir, expand_env)))

    for part_id, part in mesh_parts.items():
        if part.get("source_id") not in mesh_sources:
            errors.append(f"mesh part {part_id} references missing source {part.get('source_id')!r}")
        if part.get("link_id") not in links:
            errors.append(f"mesh part {part_id} references missing link {part.get('link_id')!r}")
        for gaussian_id in part.get("reference_gaussian_part_ids", []):
            if gaussian_id not in gaussians:
                errors.append(f"mesh part {part_id} references missing Gaussian part {gaussian_id!r}")

    missing_files = []
    for owner, path in input_files:
        if not path.is_file():
            missing_files.append({"owner": owner, "path": str(path)})
    if missing_files:
        errors.extend(f"input file not found for {item['owner']}: {item['path']}" for item in missing_files)
    checks["input_files"] = {
        "checked_count": len(input_files),
        "existing_count": len(input_files) - len(missing_files),
        "missing": missing_files,
    }

    def body_to_link(body, joint_id, side):
        reference_type = body.get("reference_type")
        reference_id = body.get("reference_id")
        if reference_type == "link":
            if reference_id in links:
                return reference_id
        elif reference_type == "mesh_part":
            if reference_id in mesh_parts:
                return mesh_parts[reference_id].get("link_id")
        elif reference_type == "gaussian_part":
            if reference_id in gaussians:
                return gaussians[reference_id].get("link_id")
        errors.append(
            f"joint {joint_id} {side} cannot resolve {reference_type!r}/{reference_id!r} to a link"
        )
        return None

    edges = []
    resolved_joint_bodies = []
    for joint_id, joint in joints.items():
        for side in ("body0", "body1"):
            body = joint.get(side, {})
            if (
                config.get("validation", {}).get("require_joint_bodies_resolve_to_links")
                and body.get("reference_type") != "link"
            ):
                errors.append(
                    f"joint {joint_id} {side} must directly reference a Link Xform; "
                    f"got {body.get('reference_type')!r}"
                )
        body0_link = body_to_link(joint.get("body0", {}), joint_id, "body0")
        body1_link = body_to_link(joint.get("body1", {}), joint_id, "body1")
        resolved_joint_bodies.append(
            {"joint_id": joint_id, "body0_link": body0_link, "body1_link": body1_link}
        )
        if body0_link and body1_link:
            if body0_link == body1_link:
                errors.append(f"joint {joint_id} connects link {body0_link} to itself")
            else:
                edges.append((body0_link, body1_link))
        limits = joint.get("limits", {})
        if limits.get("enabled", False):
            lower = limits.get("lower_deg")
            upper = limits.get("upper_deg")
            if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in (lower, upper)):
                errors.append(f"joint {joint_id} has non-finite limits")
            elif lower > upper:
                errors.append(f"joint {joint_id} lower limit exceeds upper limit")
    checks["resolved_joint_bodies"] = resolved_joint_bodies

    enabled_link_ids = {item_id for item_id, item in links.items() if item.get("enabled", True)}
    adjacency = {link_id: set() for link_id in enabled_link_ids}
    for body0, body1 in edges:
        if body0 in adjacency and body1 in adjacency:
            adjacency[body0].add(body1)
            adjacency[body1].add(body0)
    visited = set()
    if adjacency:
        pending = [next(iter(adjacency))]
        while pending:
            link_id = pending.pop()
            if link_id in visited:
                continue
            visited.add(link_id)
            pending.extend(adjacency[link_id] - visited)
    connected = visited == enabled_link_ids
    chain = connected and len(edges) == max(0, len(enabled_link_ids) - 1) and all(
        len(neighbors) <= 2 for neighbors in adjacency.values()
    )
    checks["articulation_graph"] = {
        "enabled_links": sorted(enabled_link_ids),
        "edges": [list(edge) for edge in edges],
        "connected": connected,
        "is_chain": chain,
    }
    if config.get("validation", {}).get("require_connected_articulation") and not connected:
        errors.append("articulation graph is not connected")
    if config.get("validation", {}).get("required_topology") == "chain" and not chain:
        errors.append("articulation graph is not a chain")

    expected = config.get("validation", {}).get("expected_counts", {})
    actual = {
        "enabled_links": sum(item.get("enabled", True) for item in links.values()),
        "enabled_joints": sum(item.get("enabled", True) for item in joints.values()),
        "enabled_gaussian_parts": sum(item.get("enabled", True) for item in gaussians.values()),
        "enabled_mesh_parts": sum(item.get("enabled", True) for item in mesh_parts.values()),
    }
    checks["counts"] = {"expected": expected, "actual": actual}
    for name, expected_value in expected.items():
        if expected_value is not None and actual.get(name) != expected_value:
            errors.append(f"count mismatch for {name}: expected {expected_value}, actual {actual.get(name)}")

    calibration_file_value = config.get("paths", {}).get("joint_calibration_file")
    calibration_path = _resolve_path(calibration_file_value, config_dir, expand_env)
    calibration = None
    if not calibration_path.is_file():
        errors.append(f"joint calibration file not found: {calibration_path}")
    else:
        calibration = _read_json(calibration_path)
        if calibration.get("schema_version") not in ("1.0", "1.1"):
            errors.append(
                f"unsupported calibration schema_version: {calibration.get('schema_version')!r}"
            )
        calibration_joints = _unique_index(calibration.get("joints", []), "calibration.joints", errors)
        for joint_id, joint in joints.items():
            geometry = joint.get("geometry", {})
            if geometry.get("source") != "calibration_file":
                continue
            calibration_id = geometry.get("calibration_id")
            entry = calibration_joints.get(calibration_id)
            if entry is None:
                errors.append(f"joint {joint_id} references missing calibration {calibration_id!r}")
                continue
            center = geometry.get("center_override") or entry.get("center")
            axis = geometry.get("axis_override") or entry.get("axis")
            if center is None or axis is None:
                blockers.append(f"joint {joint_id} center/axis calibration is unresolved")
                continue
            if not _finite_vector(center, 3):
                errors.append(f"joint {joint_id} calibration center must be a finite 3-vector")
            if not _finite_vector(axis, 3):
                errors.append(f"joint {joint_id} calibration axis must be a finite 3-vector")
            else:
                axis_length = math.sqrt(sum(float(item) * float(item) for item in axis))
                if abs(axis_length - 1.0) > 1.0e-6:
                    errors.append(
                        f"joint {joint_id} calibration axis is not normalized: length={axis_length}"
                    )
            configured_frame = geometry.get("coordinate_frame")
            calibration_frame = calibration.get("coordinate_frame", {}).get("name")
            if configured_frame != calibration_frame:
                errors.append(
                    f"joint {joint_id} coordinate frame mismatch: "
                    f"config={configured_frame!r}, calibration={calibration_frame!r}"
                )
            selected_mesh_ids = set(entry.get("selection", {}).get("source_mesh_part_ids", []))
            expected_mesh_ids = {
                part_id
                for part_id, part in mesh_parts.items()
                if part.get("link_id") in (body_to_link(joint.get("body0", {}), joint_id, "body0"),
                                           body_to_link(joint.get("body1", {}), joint_id, "body1"))
            }
            if selected_mesh_ids and selected_mesh_ids != expected_mesh_ids:
                errors.append(
                    f"joint {joint_id} validation Mesh set mismatch: "
                    f"expected={sorted(expected_mesh_ids)}, got={sorted(selected_mesh_ids)}"
                )
            validation = entry.get("validation")
            if entry.get("method") == "reference_joint_migration_v1":
                if not isinstance(validation, dict) or validation.get("status") != "passed":
                    blockers.append(f"joint {joint_id} migrated calibration has not passed validation")
        migration = calibration.get("migration")
        if migration is not None:
            if migration.get("one_time_operation") is not True:
                errors.append("calibration migration must be marked as a one-time operation")
            if migration.get("normal_build_dependency") is not False:
                errors.append("historical migration must not be a normal build dependency")
    checks["calibration_file"] = str(calibration_path)

    assignment_file_value = config.get("paths", {}).get("mesh_component_assignment_file")
    if assignment_file_value:
        assignment_path = _resolve_path(assignment_file_value, config_dir, expand_env)
        if not assignment_path.is_file():
            errors.append(f"Mesh component assignment file not found: {assignment_path}")
        else:
            assignment = _read_json(assignment_path)
            if assignment.get("kind") != "exact_mesh_component_assignment":
                errors.append("Mesh component assignment has an unsupported kind")
            enabled_mesh_ids = {
                part_id for part_id, part in mesh_parts.items() if part.get("enabled", True)
            }
            assigned_mesh_ids = {
                item.get("mesh_part_id") for item in assignment.get("assignments", [])
            }
            if assigned_mesh_ids != enabled_mesh_ids:
                errors.append(
                    "Mesh component assignment part set mismatch: "
                    f"expected={sorted(enabled_mesh_ids)}, got={sorted(assigned_mesh_ids)}"
                )
            if assignment.get("component_count") != len(assignment.get("assignments", [])):
                errors.append("Mesh component assignment count mismatch")
            source_id = next(
                (
                    item.get("source_id")
                    for item in mesh_parts.values()
                    if item.get("enabled", True)
                ),
                None,
            )
            source_config = mesh_sources.get(source_id, {})
            source_file = source_config.get("source_file")
            if source_file:
                current_mesh_path = _resolve_path(source_file, config_dir, expand_env)
                expected_hash = assignment.get("source", {}).get("file_sha256")
                if current_mesh_path.is_file() and _sha256(current_mesh_path) != expected_hash:
                    errors.append("Mesh component assignment source SHA-256 mismatch")
            if assignment.get("source", {}).get("prim_path") != source_config.get(
                "source_prim_path"
            ):
                errors.append("Mesh component assignment source Prim mismatch")
            checks["mesh_component_assignment_file"] = str(assignment_path)

    if config.get("articulation", {}).get("mode") != "floating":
        warnings.append("candidate articulation mode is not floating")
    if config.get("articulation", {}).get("fixed_base", {}).get("enabled"):
        errors.append("floating candidate must not enable fixed_base")

    report = {
        "schema_version": "1.0",
        "kind": "candidate_static_validation_report",
        "config_file": str(config_path),
        "valid_for_candidate_review": not errors,
        "ready_for_formal_build": not errors and not blockers,
        "errors": errors,
        "warnings": warnings,
        "build_blockers": blockers,
        "checks": checks,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
