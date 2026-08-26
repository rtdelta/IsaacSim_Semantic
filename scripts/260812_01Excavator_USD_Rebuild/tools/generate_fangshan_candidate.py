#!/usr/bin/env python3
"""Generate the Fangshan candidate build and calibration configs from scans."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path, PurePosixPath


PART_ORDER = [
    "track",
    "cab",
    "boom",
    "arm",
    "bucket_without_teeth",
    "tooth_01_front",
    "tooth_01_back",
    "tooth_02_front",
    "tooth_02_back",
    "tooth_03_front",
    "tooth_03_back",
    "tooth_04_front",
    "tooth_04_back",
    "tooth_05_front",
    "tooth_05_back",
]

LINK_BY_PART = {
    "track": "track",
    "cab": "cab",
    "boom": "boom",
    "arm": "arm",
    "bucket_without_teeth": "bucket",
    **{f"tooth_{number:02d}_{side}": "bucket" for number in range(1, 6) for side in ("front", "back")},
}

JOINT_REFERENCE_NAMES = {
    "track_cab_joint": "track_operator_cab_joint",
    "cab_boom_joint": "platform_boom_joint",
    "boom_arm_joint": "boom_small_arm_joint",
    "arm_bucket_joint": "small_arm_bucket_joint",
}

JOINT_LINKS = {
    "track_cab_joint": ("track", "cab"),
    "cab_boom_joint": ("cab", "boom"),
    "boom_arm_joint": ("boom", "arm"),
    "arm_bucket_joint": ("arm", "bucket"),
}


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _semantic_label(part_id: str) -> str:
    if part_id.startswith("tooth_"):
        return f"teeth_{part_id.removeprefix('tooth_')}_3DGS"
    return f"{part_id}_3DGS"


def _gaussian_part(source_root: PurePosixPath, part_id: str):
    gaussian_id = f"{part_id}_gaussian"
    return {
        "id": gaussian_id,
        "enabled": True,
        "source_file": str(source_root / "ply_parts" / f"{part_id}.ply"),
        "link_id": LINK_BY_PART[part_id],
        "relative_prim_path": f"Visual/Gaussian/{part_id}",
        "units_to_meters_override": None,
        "visibility_override": None,
        "semantic": {
            "enabled": True,
            "label": _semantic_label(part_id),
            "type": "class",
        },
    }


def _bounds(parts):
    minimum = [min(part["position"]["minimum"][axis] for part in parts) for axis in range(3)]
    maximum = [max(part["position"]["maximum"][axis] for part in parts) for axis in range(3)]
    return {"min": minimum, "max": maximum}


def _reference_joint(reference_manifest, old_name):
    return next((item for item in reference_manifest["joints"] if item["name"] == old_name), None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-template", required=True, type=Path)
    parser.add_argument("--calibration-template", required=True, type=Path)
    parser.add_argument("--gaussian-manifest", required=True, type=Path)
    parser.add_argument("--mesh-manifest", required=True, type=Path)
    parser.add_argument("--reference-manifest", required=True, type=Path)
    parser.add_argument("--remote-input-root", required=True)
    parser.add_argument("--remote-project-root", required=True)
    parser.add_argument("--output-config", required=True, type=Path)
    parser.add_argument("--output-calibration", required=True, type=Path)
    parser.add_argument("--output-mapping", required=True, type=Path)
    args = parser.parse_args()

    config = copy.deepcopy(_read_json(args.build_template))
    calibration = copy.deepcopy(_read_json(args.calibration_template))
    gaussian_manifest = _read_json(args.gaussian_manifest)
    mesh_manifest = _read_json(args.mesh_manifest)
    reference_manifest = _read_json(args.reference_manifest)

    scanned_parts = {item["id"]: item for item in gaussian_manifest["parts"]}
    if set(scanned_parts) != set(PART_ORDER):
        missing = sorted(set(PART_ORDER) - set(scanned_parts))
        unexpected = sorted(set(scanned_parts) - set(PART_ORDER))
        raise RuntimeError(f"unexpected PLY inventory; missing={missing}, unexpected={unexpected}")
    if gaussian_manifest["error_count"] != 0:
        raise RuntimeError("PLY manifest contains inspection errors")
    if mesh_manifest["mesh_count"] != 1:
        raise RuntimeError(f"expected one combined Mesh, found {mesh_manifest['mesh_count']}")

    mesh_record = mesh_manifest["meshes"][0]
    if mesh_record["prim_path"] != "/World/mesh_":
        raise RuntimeError(f"unexpected combined Mesh prim: {mesh_record['prim_path']}")

    input_root = PurePosixPath(args.remote_input_root)
    remote_project_root = PurePosixPath(args.remote_project_root)
    config["project"]["description"] = (
        "Candidate floating Fangshan excavator generated from the verified 15-part 3DGS PLY inventory "
        "and the combined Mesh USD; old USD is reference-only"
    )
    config["paths"]["joint_calibration_file"] = f"./{args.output_calibration.name}"
    config["paths"]["mesh_component_assignment_file"] = (
        "./fangshan_candidate.mesh_component_assignment.json"
    )
    config["paths"]["output_directory"] = str(remote_project_root / "outputs" / "fangshan_candidate")
    config["gaussian"]["parts"] = [_gaussian_part(input_root, part_id) for part_id in PART_ORDER]

    config["mesh"]["sources"][0]["source_file"] = str(
        input_root / "mesh_parts" / "拆分成五部分的mesh.usd"
    )
    config["mesh"]["sources"][0]["source_prim_path"] = mesh_record["prim_path"]
    # The authored metadata says 0.01 m/unit, but the numeric Mesh bounds match
    # the PLY meter-space bounds directly. Keep this explicit pending approval.
    config["mesh"]["sources"][0]["units_to_meters"] = 1.0

    for joint in config["joints"]:
        try:
            body0_link, body1_link = JOINT_LINKS[joint["id"]]
        except KeyError as exc:
            raise RuntimeError(f"unexpected Fangshan joint id: {joint.get('id')!r}") from exc
        joint["body0"] = {
            "reference_type": "link",
            "reference_id": body0_link,
            "prim_path": None,
        }
        joint["body1"] = {
            "reference_type": "link",
            "reference_id": body1_link,
            "prim_path": None,
        }

    gaussian_ids_by_link = {
        link_id: [f"{part_id}_gaussian" for part_id in PART_ORDER if LINK_BY_PART[part_id] == link_id]
        for link_id in ("track", "cab", "boom", "arm", "bucket")
    }
    for mesh_part in config["mesh"]["parts"]:
        mesh_part["reference_gaussian_part_ids"] = gaussian_ids_by_link[mesh_part["link_id"]]

    config["validation"]["expected_counts"] = {
        "enabled_links": 5,
        "enabled_joints": 4,
        "enabled_gaussian_parts": 15,
        "enabled_mesh_parts": 5,
    }

    mesh_source_path = input_root / "mesh_parts" / "拆分成五部分的mesh.usd"
    calibration["source"]["source_file"] = str(mesh_source_path)
    calibration["source"]["source_prim_path"] = mesh_record["prim_path"]
    calibration["source"]["source_file_sha256"] = mesh_manifest["source_file_sha256"]
    calibration["coordinate_frame"]["units_to_meters"] = 1.0
    calibration["coordinate_frame"]["up_axis"] = mesh_manifest["stage_up_axis"]
    migrated_calibration = calibration.get("migration", {}).get("status") == "completed"
    if not migrated_calibration:
        for joint in calibration["joints"]:
            joint["method"] = "reference_joint_migration_v1"
            joint["center"] = None
            joint["axis"] = None
            joint["fit"] = {key: None for key in joint["fit"]}
            joint["validation"] = None
            joint["provenance"]["notes"] = (
                "Pending the one-time Fangshan reference Joint migration and current Mesh validation; "
                "historical USD local frames must never be copied verbatim."
            )

    gaussian_bounds = _bounds(list(scanned_parts.values()))
    mesh_bounds = mesh_record["numeric_point_bounds"]
    bounds_difference = {
        "min_mesh_minus_gaussian": [
            mesh_bounds["min"][axis] - gaussian_bounds["min"][axis] for axis in range(3)
        ],
        "max_mesh_minus_gaussian": [
            mesh_bounds["max"][axis] - gaussian_bounds["max"][axis] for axis in range(3)
        ],
    }

    historical_joints = []
    for new_name, old_name in JOINT_REFERENCE_NAMES.items():
        item = _reference_joint(reference_manifest, old_name)
        if item is None:
            raise RuntimeError(f"reference joint not found: {old_name}")
        historical_joints.append(
            {
                "candidate_joint_id": new_name,
                "reference_joint_name": old_name,
                "reference_body_relationships": item["relationships"],
                "reference_axis_token": item["attributes"].get("physics:axis"),
                "reference_local_pos0": item["attributes"].get("physics:localPos0"),
                "reference_local_rot0": item["attributes"].get("physics:localRot0"),
                "reference_lower_limit_deg": item["attributes"].get("physics:lowerLimit"),
                "reference_upper_limit_deg": item["attributes"].get("physics:upperLimit"),
                "adoption": {
                    "topology_and_body_order": "adopted_as_link_xform_relationships",
                    "limits": "adopted_from_reference_motion_convention",
                    "center_and_axis": "pending_one_time_world_line_migration_and_mesh_validation",
                },
            }
        )

    mapping = {
        "schema_version": "1.0",
        "kind": "fangshan_candidate_mapping",
        "candidate_status": "requires_user_confirmation_before_build",
        "independence": {
            "build_depends_on_old_excavator_usd": False,
            "old_excavator_usd_role": (
                "one-time migration input for Joint world rotation lines and motion conventions; "
                "excluded from all normal builds after calibration is generated"
            ),
        },
        "inputs": {
            "gaussian_part_count": len(PART_ORDER),
            "gaussian_total_splat_count": gaussian_manifest["total_vertex_count"],
            "all_gaussian_parts_standard_3dgs": all(
                part["is_standard_3dgs"] for part in scanned_parts.values()
            ),
            "mesh_source": {
                "path": str(mesh_source_path),
                "sha256": mesh_manifest["source_file_sha256"],
                "prim_path": mesh_record["prim_path"],
                "point_count": mesh_record["point_count"],
                "face_count": mesh_record["face_count"],
                "connected_components": mesh_record.get("connected_components"),
            },
        },
        "coordinate_and_units_candidate": {
            "root_prim_path": config["stage"]["root_prim_path"],
            "target_up_axis": config["stage"]["up_axis"],
            "target_meters_per_unit": config["stage"]["meters_per_unit"],
            "origin": "track Gaussian OBB center",
            "mesh_authored_meters_per_unit": mesh_manifest["stage_meters_per_unit"],
            "mesh_candidate_numeric_units_to_meters": 1.0,
            "gaussian_union_numeric_bounds": gaussian_bounds,
            "mesh_numeric_bounds": {"min": mesh_bounds["min"], "max": mesh_bounds["max"]},
            "numeric_bounds_difference_m": bounds_difference,
            "unit_decision_status": "candidate_pending_user_confirmation",
        },
        "links": [
            {
                "link_id": link_id,
                "mesh_part_id": f"{link_id}_mesh",
                "gaussian_part_ids": gaussian_ids_by_link[link_id],
            }
            for link_id in ("track", "cab", "boom", "arm", "bucket")
        ],
        "gaussian_parts": [
            {
                "part_id": part_id,
                "file": f"{part_id}.ply",
                "link_id": LINK_BY_PART[part_id],
                "semantic_label": _semantic_label(part_id),
                "splat_count": scanned_parts[part_id]["vertex_count"],
                "sha256": scanned_parts[part_id]["sha256"],
            }
            for part_id in PART_ORDER
        ],
        "joints": historical_joints,
        "deliberately_unresolved": [
            "One-time migration of four Joint world rotation lines into source Mesh numeric coordinates",
            "Current Mesh geometry validation of the four migrated rotation lines",
            "Mesh connected-component-to-link assignment validation",
            "Coordinate PCA sign and final visual uprightness validation",
        ],
    }

    _write_json(args.output_config, config)
    output_calibration_resolved = args.output_calibration.expanduser().resolve()
    calibration_template_resolved = args.calibration_template.expanduser().resolve()
    if output_calibration_resolved != calibration_template_resolved:
        _write_json(args.output_calibration, calibration)
    elif not migrated_calibration:
        raise RuntimeError(
            "refusing to overwrite an unresolved calibration template in place; choose a different output"
        )
    _write_json(args.output_mapping, mapping)
    print(
        json.dumps(
            {
                "config": str(args.output_config),
                "calibration": str(args.output_calibration),
                "mapping": str(args.output_mapping),
                "gaussian_parts": len(config["gaussian"]["parts"]),
                "links": len(config["links"]),
                "joints": len(config["joints"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
