"""Validate semantic files, frame context, render manifest, and recorded motion."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from capture_timing import CaptureTiming
from render_profile import SUPPORTED_RENDERERS
from semantic_mapping import SemanticMapping


ARTICULATION_CONTROL_MODE = "articulation_direct_position"
ROOT_CONTROL_MODE = "articulation_direct_world_pose"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def changed(values: list[list[float] | None], tolerance: float = 1e-7) -> bool:
    present = [np.asarray(value, dtype=np.float64) for value in values if value is not None]
    if len(present) < 2:
        return False
    return any(not np.allclose(present[0], value, atol=tolerance, rtol=0.0) for value in present[1:])


def require_close(label: str, actual: float, expected: float, tolerance: float = 1e-9) -> None:
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance):
        raise RuntimeError(f"{label}: expected {expected:.12f}, got {actual:.12f}")


def validate_render_manifest(render: dict[str, Any]) -> None:
    if render.get("mismatches"):
        raise RuntimeError(f"Render settings contain mismatches: {render['mismatches']}")

    profile = render.get("profile", {})
    renderer_record = render.get("renderer", {})
    profile_renderer = profile.get("renderer")
    requested_renderer = renderer_record.get("requested")
    effective_renderer = renderer_record.get("effective")
    formal_renderer = profile_renderer in SUPPORTED_RENDERERS or requested_renderer in SUPPORTED_RENDERERS
    if not formal_renderer:
        # Schema-v1 outputs predate authoritative renderer read-back. Preserve
        # validation compatibility while requiring all schema-v2 profiles below.
        return
    if profile_renderer not in SUPPORTED_RENDERERS:
        raise RuntimeError(f"Unsupported profile renderer: {profile_renderer!r}")
    if requested_renderer != profile_renderer or effective_renderer != profile_renderer:
        raise RuntimeError(
            "Renderer selection did not take effect: "
            f"profile={profile_renderer!r}, requested={requested_renderer!r}, "
            f"effective={effective_renderer!r}"
        )

    capture = render.get("capture", {})
    sampling = render.get("sampling", {})
    rt_subframes = int(capture.get("rt_subframes", sampling.get("rt_subframes", 0)))
    if rt_subframes <= 0:
        raise RuntimeError("Render manifest must record positive rt_subframes")

    if profile_renderer == "RealTimePathTracing":
        if sampling.get("model") != "realtime_temporal_subframes":
            raise RuntimeError("RealTimePathTracing uses the realtime temporal sampling model")
        if sampling.get("dlss_exec_mode") not in {0, 1, 2, 3}:
            raise RuntimeError("RealTimePathTracing must record a valid DLSS execMode")
        if "spp_per_render_frame" in sampling:
            raise RuntimeError("RealTimePathTracing manifest must not report PathTracing SPP")
    else:
        if sampling.get("model") != "path_tracing_spp":
            raise RuntimeError("PathTracing uses the path_tracing_spp sampling model")
        spp = int(sampling.get("spp_per_render_frame", 0))
        total_spp = int(sampling.get("total_spp_cap", -1))
        nominal_spp = int(sampling.get("nominal_spp_per_output", 0))
        planned_spp = int(sampling.get("planned_spp_per_output", 0))
        if not 1 <= spp <= 32:
            raise RuntimeError(f"PathTracing spp is invalid: {spp}")
        if total_spp < 0 or (total_spp != 0 and total_spp < spp):
            raise RuntimeError(f"PathTracing totalSpp is invalid: {total_spp}")
        if nominal_spp != spp * rt_subframes:
            raise RuntimeError(
                f"PathTracing nominal sample budget is inconsistent: {nominal_spp}"
            )
        expected_planned = min(nominal_spp, total_spp) if total_spp > 0 else nominal_spp
        if planned_spp != expected_planned:
            raise RuntimeError(
                f"PathTracing planned sample budget is inconsistent: {planned_spp}"
            )
        if sampling.get("accumulation_reset_on_time_change") is not True:
            raise RuntimeError("PathTracing accumulation reset on time change is not enabled")


def validate_manifest_v2(run_config: dict[str, Any], expected: int) -> CaptureTiming:
    if run_config.get("status") != "complete":
        raise RuntimeError(f"Run manifest status is not complete: {run_config.get('status')!r}")
    if int(run_config.get("frames", -1)) != expected:
        raise RuntimeError(
            f"Run manifest declares {run_config.get('frames')} frames, expected {expected}"
        )
    render = run_config.get("render", {})
    validate_render_manifest(render)
    preflight = run_config.get("preflight", {})
    if run_config.get("strict_stage") and not preflight.get("passed", False):
        raise RuntimeError("Strict Stage preflight did not pass")
    writer = run_config.get("writer", {})
    if int(writer.get("pending", -1)) != 0:
        raise RuntimeError(f"Writer has pending frame contexts: {writer.get('pending')}")
    schema_version = int(run_config.get("schema_version", 1))
    isolated_enabled = bool(
        run_config.get("excavator_only_capture", {}).get("enabled", False)
    )
    front_teeth_enabled = bool(
        run_config.get("front_teeth_only_capture", {}).get("enabled", False)
    )
    enabled_variant_count = 1
    if schema_version >= 5 and isolated_enabled:
        enabled_variant_count += 1
    if schema_version >= 6 and front_teeth_enabled:
        enabled_variant_count += 1
    expected_writer_completions = expected * enabled_variant_count
    if int(writer.get("completed", -1)) != expected_writer_completions:
        raise RuntimeError(
            f"Writer completed {writer.get('completed')} captures, "
            f"expected {expected_writer_completions}"
        )
    if schema_version >= 7:
        if int(writer.get("committed_frames", -1)) != expected:
            raise RuntimeError(
                f"Writer committed {writer.get('committed_frames')} frames, "
                f"expected {expected}"
            )
        transition = run_config.get("effective_config", {}).get(
            "variant_transition", {}
        )
        settle_render_count = int(transition.get("settle_render_count", 0))
        probe_groups_per_frame = 2 + int(isolated_enabled) + int(front_teeth_enabled)
        minimum_probes = expected * probe_groups_per_frame * settle_render_count
        if int(writer.get("completed_probes", -1)) < minimum_probes:
            raise RuntimeError(
                f"Writer completed {writer.get('completed_probes')} probes, "
                f"expected at least {minimum_probes}"
            )
    if schema_version >= 5:
        completed_by_variant = writer.get("completed_by_variant", {})
        expected_by_variant = {"full_scene": expected, "excavator_only": 0}
        if schema_version >= 6:
            expected_by_variant["front_teeth_only"] = 0
        if isolated_enabled:
            expected_by_variant["excavator_only"] = expected
        if schema_version >= 6 and front_teeth_enabled:
            expected_by_variant["front_teeth_only"] = expected
        if completed_by_variant != expected_by_variant:
            raise RuntimeError(
                "Writer variant completion counts do not match: "
                f"{completed_by_variant} != {expected_by_variant}"
            )
    return CaptureTiming(
        physics_hz=int(run_config["physics_hz"]),
        capture_fps=int(run_config["capture_fps"]),
        capture_initial_frame=bool(run_config.get("capture_initial_frame", False)),
        static=run_config.get("capture_mode") == "static",
    )


def validate_manifest_v3(run_config: dict[str, Any]) -> None:
    """Validate the direct-Articulation control contract added in schema v3."""

    motion_enabled = bool(run_config.get("motion_enabled"))
    motion_control = run_config.get("motion_control")
    if not isinstance(motion_control, dict):
        raise RuntimeError("Schema-v3 manifest must contain motion_control")
    if motion_control.get("mode") != ARTICULATION_CONTROL_MODE:
        raise RuntimeError(
            "Schema-v3 motion_control mode must be "
            f"{ARTICULATION_CONTROL_MODE!r}"
        )

    profile = motion_control.get("joint_profile")
    if not isinstance(profile, dict):
        raise RuntimeError("Schema-v3 manifest must record a joint-control profile")
    logical_names = profile.get("logical_joint_names")
    if logical_names != ["cab", "boom", "small_arm", "bucket"]:
        raise RuntimeError(
            "Joint-control profile must preserve recorder column order "
            "['cab', 'boom', 'small_arm', 'bucket']"
        )
    tolerance = float(profile.get("readback_tolerance_degrees", 0.0))
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise RuntimeError("Joint readback tolerance must be positive and finite")

    if not motion_enabled:
        return

    preflight = run_config.get("preflight", {})
    articulation_preflight = preflight.get("articulation")
    if not isinstance(articulation_preflight, dict) or not articulation_preflight.get(
        "passed", False
    ):
        raise RuntimeError("Motion capture requires a passing Articulation Stage preflight")

    bootstrap_steps = motion_control.get("bootstrap_steps")
    setup_steps = motion_control.get("setup_steps")
    if not isinstance(bootstrap_steps, int) or isinstance(bootstrap_steps, bool):
        raise RuntimeError("Articulation bootstrap_steps must be an integer")
    if bootstrap_steps < 0:
        raise RuntimeError("Articulation bootstrap_steps cannot be negative")
    if setup_steps != 1:
        raise RuntimeError("Direct Articulation playback requires exactly one setup step")

    binding = motion_control.get("binding")
    if not isinstance(binding, dict):
        raise RuntimeError("Motion capture manifest does not contain an Articulation binding")
    if binding.get("control_mode") != ARTICULATION_CONTROL_MODE:
        raise RuntimeError("Articulation binding control mode is inconsistent")
    adapter = binding.get("adapter")
    if not isinstance(adapter, dict) or not adapter.get("bound") or not adapter.get("ready"):
        raise RuntimeError("Articulation adapter was not recorded as bound and ready")
    selected_names = binding.get("dof_names")
    if not isinstance(selected_names, dict) or set(selected_names) != set(logical_names):
        raise RuntimeError("Articulation binding does not identify all logical DOFs")
    expected_dof_order = [selected_names[name] for name in logical_names]
    if adapter.get("ordered_dof_names") != expected_dof_order:
        raise RuntimeError("Articulation adapter DOF order does not match the excavator contract")


def validate_manifest_v8(run_config: dict[str, Any]) -> None:
    """Validate the optional floating-root playback contract added in schema v8."""

    motion_control = run_config.get("motion_control", {})
    root_config = motion_control.get("root_pose_playback")
    if not isinstance(root_config, dict) or type(root_config.get("enabled")) is not bool:
        raise RuntimeError("Schema-v8 manifest must record root_pose_playback")
    enabled = root_config["enabled"]
    expected_root_mode = ROOT_CONTROL_MODE if enabled else None
    if motion_control.get("root_control_mode") != expected_root_mode:
        raise RuntimeError("Root control mode is inconsistent with root playback enablement")
    if not enabled:
        return
    if run_config.get("motion_enabled") is not True:
        raise RuntimeError("Root-pose playback requires motion_enabled=true")
    for field_name in (
        "position_tolerance_meters",
        "orientation_tolerance_degrees",
    ):
        tolerance = float(root_config.get(field_name, 0.0))
        if not math.isfinite(tolerance) or tolerance <= 0:
            raise RuntimeError(f"Root playback {field_name} must be positive and finite")
    if root_config.get("coordinate_mode") not in {
        "absolute_world",
        "relative_to_initial",
    }:
        raise RuntimeError("Root playback coordinate_mode is invalid")
    if root_config.get("position_interpolation") != "linear":
        raise RuntimeError("Root position interpolation must be linear")
    if root_config.get("orientation_interpolation") != "slerp":
        raise RuntimeError("Root orientation interpolation must be slerp")
    if root_config.get("apply_policy") not in {
        "authoritative_pose",
        "physics_accepted",
    }:
        raise RuntimeError("Root apply_policy is invalid")
    if root_config.get("zero_root_velocity") is not True:
        raise RuntimeError("Root velocity clearing must be enabled")

    profile = motion_control.get("joint_profile", {})
    if profile.get("require_fixed_base") is not False:
        raise RuntimeError("Root playback profile must not require a fixed base")
    if profile.get("require_floating_base") is not True:
        raise RuntimeError("Root playback profile must require a floating base")
    if profile.get("root_pose_playback_supported") is not True:
        raise RuntimeError("Root playback profile does not declare root support")

    trajectory = run_config.get("trajectory", {})
    if trajectory.get("schema") != "joint_and_root_pose_v1":
        raise RuntimeError("Root playback trajectory schema is inconsistent")
    if trajectory.get("root_pose_included") is not True:
        raise RuntimeError("Root playback trajectory does not record root pose columns")
    if trajectory.get("root_position_interpolation") != "linear":
        raise RuntimeError("Manifest does not record linear root position interpolation")
    if trajectory.get("root_orientation_interpolation") != "slerp":
        raise RuntimeError("Manifest does not record SLERP root orientation interpolation")

    articulation = run_config.get("preflight", {}).get("articulation", {})
    if articulation.get("passed") is not True:
        raise RuntimeError("Root playback requires a passing articulation preflight")
    if articulation.get("root_body_path") is None:
        raise RuntimeError("Root playback preflight did not resolve a root body")
    meters_per_unit = articulation.get("meters_per_unit")
    if meters_per_unit is None or not math.isclose(
        float(meters_per_unit), 1.0, rel_tol=0.0, abs_tol=1.0e-12
    ):
        raise RuntimeError("Root playback target Stage must use metersPerUnit=1")
    if articulation.get("up_axis") != "Z":
        raise RuntimeError("Root playback target Stage must be Z-up")

    binding = motion_control.get("binding", {})
    if binding.get("root_control_mode") != ROOT_CONTROL_MODE:
        raise RuntimeError("Root playback binding control mode is inconsistent")
    if binding.get("root_body_path") != articulation.get("root_body_path"):
        raise RuntimeError("Root playback binding and preflight root body differ")
    if binding.get("adapter", {}).get("supports_root_world_pose") is not True:
        raise RuntimeError("Articulation adapter root world-pose support was not recorded")
    binding_root_config = binding.get("root_pose_playback", {})
    coordinate_contract = binding_root_config.get("coordinate_contract")
    if not isinstance(coordinate_contract, dict):
        raise RuntimeError("Root playback coordinate contract was not recorded")
    if coordinate_contract.get("csv_position_unit") != "meter":
        raise RuntimeError("Root playback CSV position unit is not meter")
    if coordinate_contract.get("csv_quaternion_order") != "wxyz":
        raise RuntimeError("Root playback CSV quaternion order is not wxyz")
    if not math.isclose(
        float(coordinate_contract.get("target_meters_per_unit", 0.0)),
        float(articulation["meters_per_unit"]),
        rel_tol=0.0,
        abs_tol=1.0e-12,
    ) or coordinate_contract.get("target_up_axis") != articulation.get("up_axis"):
        raise RuntimeError("Root playback binding target coordinate system is inconsistent")
    source_stage_path = coordinate_contract.get("source_stage_path")
    if int(run_config.get("schema_version", 1)) < 9 and (
        not isinstance(source_stage_path, str) or not source_stage_path.strip()
    ):
        raise RuntimeError("Root playback source Stage path was not recorded")
    _finite_vector(
        -1,
        "source initial root position",
        coordinate_contract.get("source_initial_position_meters"),
        3,
    )
    _unit_quaternion(
        -1,
        "source initial root orientation",
        coordinate_contract.get("source_initial_orientation_wxyz"),
    )
    _finite_vector(
        -1,
        "target initial root position",
        coordinate_contract.get("target_initial_position_meters"),
        3,
    )
    _unit_quaternion(
        -1,
        "target initial root orientation",
        coordinate_contract.get("target_initial_orientation_wxyz"),
    )


def validate_manifest_v9(run_config: dict[str, Any]) -> None:
    """Validate optional trajectory-sidecar provenance added in schema v9."""

    validate_manifest_v8(run_config)
    motion_control = run_config.get("motion_control", {})
    root_config = motion_control.get("root_pose_playback", {})
    if root_config.get("enabled") is not True:
        return

    trajectory = run_config.get("trajectory", {})
    provenance = trajectory.get("metadata_provenance")
    if not isinstance(provenance, dict):
        raise RuntimeError("Schema-v9 root trajectory metadata provenance is missing")
    if motion_control.get("trajectory_metadata_provenance") != provenance:
        raise RuntimeError("Trajectory metadata provenance records are inconsistent")

    present = provenance.get("present")
    required = provenance.get("required")
    if type(present) is not bool or type(required) is not bool:
        raise RuntimeError("Trajectory metadata provenance flags must be boolean")
    expected_path = provenance.get("expected_sidecar_path")
    if not isinstance(expected_path, str) or not expected_path.strip():
        raise RuntimeError("Trajectory metadata expected sidecar path was not recorded")

    basis = provenance.get("source_contract_basis")
    trajectory_metadata = trajectory.get("metadata")
    motion_metadata = motion_control.get("trajectory_metadata")
    input_metadata = run_config.get("inputs", {}).get("trajectory_metadata")
    coordinate_contract = (
        motion_control.get("binding", {})
        .get("root_pose_playback", {})
        .get("coordinate_contract", {})
    )
    if coordinate_contract.get("source_contract_basis") != basis:
        raise RuntimeError("Root coordinate-contract provenance is inconsistent")

    if present:
        if basis != "recorder_sidecar":
            raise RuntimeError("Present trajectory metadata must use recorder_sidecar basis")
        if not isinstance(trajectory_metadata, dict) or trajectory_metadata != motion_metadata:
            raise RuntimeError("Present trajectory metadata records are inconsistent")
        if not isinstance(input_metadata, dict):
            raise RuntimeError("Present trajectory metadata input file was not recorded")
        source_stage_path = coordinate_contract.get("source_stage_path")
        if not isinstance(source_stage_path, str) or not source_stage_path.strip():
            raise RuntimeError("Recorder metadata did not provide a source Stage path")
        return

    if required:
        raise RuntimeError("Required trajectory metadata was not present")
    if basis != "csv_absolute_world_user_assertion":
        raise RuntimeError(
            "Metadata-less root playback must record the absolute-world CSV assertion"
        )
    if root_config.get("coordinate_mode") != "absolute_world":
        raise RuntimeError(
            "Metadata-less root playback is permitted only in absolute_world mode"
        )
    profile_contract = motion_control.get("joint_profile", {}).get(
        "trajectory_metadata", {}
    )
    if profile_contract.get("require_root_motion_metadata") is not False:
        raise RuntimeError("Joint profile did not make root trajectory metadata optional")
    if trajectory_metadata is not None or motion_metadata is not None:
        raise RuntimeError("Absent trajectory metadata must be recorded as null")
    if input_metadata is not None:
        raise RuntimeError("Absent trajectory metadata input must be recorded as null")
    if coordinate_contract.get("source_stage_path") is not None:
        raise RuntimeError(
            "Metadata-less absolute-world playback must not invent a source Stage path"
        )


def _finite_joint_values(
    frame_id: int,
    label: str,
    values: Any,
    expected_names: tuple[str, ...],
) -> dict[str, float]:
    if not isinstance(values, dict) or set(values) != set(expected_names):
        raise RuntimeError(
            f"Frame {frame_id}: {label} must contain exactly {list(expected_names)}"
        )
    result = {name: float(values[name]) for name in expected_names}
    if any(not math.isfinite(value) for value in result.values()):
        raise RuntimeError(f"Frame {frame_id}: {label} contains a non-finite value")
    return result


def _finite_vector(frame_id: int, label: str, values: Any, length: int) -> tuple[float, ...]:
    if not isinstance(values, (list, tuple)) or len(values) != length:
        raise RuntimeError(f"Frame {frame_id}: {label} must contain {length} values")
    result = tuple(float(value) for value in values)
    if any(not math.isfinite(value) for value in result):
        raise RuntimeError(f"Frame {frame_id}: {label} contains a non-finite value")
    return result


def _unit_quaternion(frame_id: int, label: str, values: Any) -> tuple[float, ...]:
    quaternion = _finite_vector(frame_id, label, values, 4)
    norm = math.sqrt(sum(value * value for value in quaternion))
    if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1.0e-5):
        raise RuntimeError(f"Frame {frame_id}: {label} is not a unit quaternion")
    return quaternion


def _quaternion_error_degrees(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    dot = max(0.0, min(1.0, abs(sum(a * b for a, b in zip(left, right)))))
    return math.degrees(2.0 * math.acos(dot))


def validate_root_motion_state(
    frame_id: int,
    motion: dict[str, Any],
    run_config: dict[str, Any],
) -> None:
    root_config = run_config["motion_control"]["root_pose_playback"]
    root_state = motion.get("root_pose")
    if not isinstance(root_state, dict):
        raise RuntimeError(f"Frame {frame_id}: motion root_pose state is missing")
    enabled = bool(root_config["enabled"])
    if root_state.get("enabled") is not enabled:
        raise RuntimeError(f"Frame {frame_id}: root playback enablement is inconsistent")
    if not enabled:
        return
    if motion.get("root_control_mode") != ROOT_CONTROL_MODE:
        raise RuntimeError(f"Frame {frame_id}: root control mode is inconsistent")
    if root_state.get("coordinate_mode") != root_config.get("coordinate_mode"):
        raise RuntimeError(f"Frame {frame_id}: root coordinate mode is inconsistent")
    if root_state.get("apply_policy") != root_config.get("apply_policy"):
        raise RuntimeError(f"Frame {frame_id}: root apply policy is inconsistent")

    commanded_position = _finite_vector(
        frame_id, "commanded root position", root_state.get("commanded_position_meters"), 3
    )
    physics_position = _finite_vector(
        frame_id,
        "physics root position",
        root_state.get("physics_readback_position_meters"),
        3,
    )
    capture_position = _finite_vector(
        frame_id, "capture root position", root_state.get("capture_position_meters"), 3
    )
    commanded_orientation = _unit_quaternion(
        frame_id,
        "commanded root orientation",
        root_state.get("commanded_orientation_wxyz"),
    )
    _unit_quaternion(
        frame_id,
        "physics root orientation",
        root_state.get("physics_readback_orientation_wxyz"),
    )
    capture_orientation = _unit_quaternion(
        frame_id,
        "capture root orientation",
        root_state.get("capture_orientation_wxyz"),
    )
    reported_error = _finite_vector(
        frame_id, "root position error", root_state.get("position_error_meters"), 3
    )
    expected_error = tuple(
        actual - commanded
        for actual, commanded in zip(capture_position, commanded_position)
    )
    for axis, (actual, expected) in enumerate(zip(reported_error, expected_error)):
        require_close(f"Frame {frame_id} root position error axis {axis}", actual, expected)
    expected_norm = math.sqrt(sum(value * value for value in expected_error))
    reported_norm = float(root_state.get("position_error_norm_meters"))
    require_close(f"Frame {frame_id} root position error norm", reported_norm, expected_norm)
    expected_orientation_error = _quaternion_error_degrees(
        commanded_orientation, capture_orientation
    )
    reported_orientation_error = float(root_state.get("orientation_error_degrees"))
    require_close(
        f"Frame {frame_id} root orientation error",
        reported_orientation_error,
        expected_orientation_error,
        tolerance=1.0e-7,
    )
    position_tolerance = float(root_config["position_tolerance_meters"])
    orientation_tolerance = float(root_config["orientation_tolerance_degrees"])
    if expected_norm > position_tolerance:
        raise RuntimeError(f"Frame {frame_id}: root position error exceeds tolerance")
    if expected_orientation_error > orientation_tolerance:
        raise RuntimeError(f"Frame {frame_id}: root orientation error exceeds tolerance")
    if "root" not in motion.get("body_world_transform", {}):
        raise RuntimeError(f"Frame {frame_id}: root body world transform is missing")


def validate_articulation_motion_state(
    frame_id: int,
    motion: dict[str, Any],
    run_config: dict[str, Any],
    joint_limits: dict[str, dict[str, Any]],
) -> None:
    """Validate command/readback/error values recorded after each physics step."""

    expected_names = tuple(
        run_config["motion_control"]["joint_profile"]["logical_joint_names"]
    )
    if motion.get("control_mode") != ARTICULATION_CONTROL_MODE:
        raise RuntimeError(f"Frame {frame_id}: unexpected motion control mode")
    commanded = _finite_joint_values(
        frame_id, "commanded_degrees", motion.get("commanded_degrees"), expected_names
    )
    actual = _finite_joint_values(
        frame_id, "actual_degrees", motion.get("actual_degrees"), expected_names
    )
    errors = _finite_joint_values(
        frame_id,
        "position_error_degrees",
        motion.get("position_error_degrees"),
        expected_names,
    )
    targets = _finite_joint_values(
        frame_id, "target_degrees", motion.get("target_degrees"), expected_names
    )
    tolerance = float(
        run_config["motion_control"]["joint_profile"]["readback_tolerance_degrees"]
    )
    for name in expected_names:
        require_close(
            f"Frame {frame_id} {name} legacy target/command",
            targets[name],
            commanded[name],
        )
        require_close(
            f"Frame {frame_id} {name} readback error",
            errors[name],
            actual[name] - commanded[name],
        )
        if abs(errors[name]) > tolerance:
            raise RuntimeError(
                f"Frame {frame_id}: {name} readback error {errors[name]} exceeds "
                f"{tolerance} degree tolerance"
            )
        joint = joint_limits.get(name)
        if joint is None:
            raise RuntimeError(f"Frame {frame_id}: no limits recorded for joint {name}")
        lower = float(joint["lower_limit_degrees"])
        upper = float(joint["upper_limit_degrees"])
        if not lower <= commanded[name] <= upper:
            raise RuntimeError(
                f"Frame {frame_id}: joint {name} command is outside limits: {commanded[name]}"
            )
        if not lower <= actual[name] <= upper:
            raise RuntimeError(
                f"Frame {frame_id}: joint {name} readback is outside limits: {actual[name]}"
            )


def validate_frame_files(
    output: Path,
    mapping: SemanticMapping,
    run_config: dict[str, Any],
    expected: int,
    timing: CaptureTiming | None,
) -> list[dict[str, Any]]:
    expected_shape = (int(run_config["resolution"][1]), int(run_config["resolution"][0]))
    valid_ids = {0, 65535, *(int(entry["id"]) for entry in mapping.schema["classes"])}
    schema_version = int(run_config.get("schema_version", 1))
    save_runtime_ids = bool(
        run_config.get("save_runtime_ids", False if schema_version >= 6 else True)
    )
    if schema_version >= 5:
        configured_folders = run_config.get("image_output_folders")
        if not isinstance(configured_folders, dict):
            raise RuntimeError("Schema-v5 manifest must contain image_output_folders")
        layouts = {
            "full_scene": (
                configured_folders["full_scene_rgb"],
                configured_folders["full_scene_semantic"],
            )
        }
        if run_config.get("excavator_only_capture", {}).get("enabled", False):
            layouts["excavator_only"] = (
                configured_folders["excavator_only_rgb"],
                configured_folders["excavator_only_semantic"],
            )
        if (
            schema_version >= 6
            and run_config.get("front_teeth_only_capture", {}).get("enabled", False)
        ):
            front_config = run_config["front_teeth_only_capture"]
            layouts["front_teeth_only"] = (
                (
                    configured_folders["front_teeth_only_rgb"]
                    if front_config.get("save_rgb", False)
                    else None
                ),
                configured_folders["front_teeth_only_semantic"],
            )
    else:
        layouts = {"full_scene": ("rgb", "")}

    full_scene_metadata: list[dict[str, Any]] = []
    for variant, (rgb_folder, semantic_folder) in layouts.items():
        semantic_root = output / semantic_folder
        metadata_root = (
            output / "metadata" / variant
            if schema_version >= 5
            else output / "metadata"
        )
        required_locations = {
            semantic_root / "semantic_id": "semantic_id_*.npy",
            semantic_root / "semantic_color": "semantic_color_*.png",
            metadata_root: "frame_*.json",
        }
        if rgb_folder is not None:
            required_locations[output / rgb_folder] = "rgb_*.png"
        if save_runtime_ids:
            required_locations[
                semantic_root / "semantic_runtime_id"
            ] = "semantic_runtime_id_*.npy"
        for folder, pattern in required_locations.items():
            count = len(list(folder.glob(pattern)))
            if count != expected:
                raise RuntimeError(
                    f"{folder} contains {count} frame files, expected {expected}"
                )

        for frame_id in range(expected):
            frame_name = f"{frame_id:04d}"
            dataset_ids = np.load(
                semantic_root / "semantic_id" / f"semantic_id_{frame_name}.npy"
            )
            if dataset_ids.shape != expected_shape or dataset_ids.dtype != np.uint16:
                raise RuntimeError(
                    f"Frame {frame_id}/{variant}: invalid semantic ID array "
                    f"{dataset_ids.shape} {dataset_ids.dtype}"
                )
            unknown_ids = set(int(value) for value in np.unique(dataset_ids)) - valid_ids
            if unknown_ids:
                raise RuntimeError(
                    f"Frame {frame_id}/{variant}: undefined semantic IDs "
                    f"{sorted(unknown_ids)}"
                )
            saved_color = np.asarray(
                Image.open(
                    semantic_root
                    / "semantic_color"
                    / f"semantic_color_{frame_name}.png"
                ).convert("RGB")
            )
            if not np.array_equal(saved_color, mapping.colorize(dataset_ids)):
                raise RuntimeError(
                    f"Frame {frame_id}/{variant}: semantic color PNG does not "
                    "match semantic ID NPY"
                )
            if rgb_folder is not None:
                with Image.open(output / rgb_folder / f"rgb_{frame_name}.png") as rgb_image:
                    if rgb_image.size != (expected_shape[1], expected_shape[0]):
                        raise RuntimeError(
                            f"Frame {frame_id}/{variant}: RGB size is {rgb_image.size}"
                        )

            metadata = load_json(metadata_root / f"frame_{frame_name}.json")
            if variant == "full_scene":
                full_scene_metadata.append(metadata)
            elif schema_version >= 8:
                reference = full_scene_metadata[frame_id]
                for field_name in (
                    "dataset_time",
                    "timeline_time",
                    "physics_step",
                    "motion",
                ):
                    if metadata.get(field_name) != reference.get(field_name):
                        raise RuntimeError(
                            f"Frame {frame_id}/{variant}: {field_name} differs from "
                            "the frozen full_scene capture"
                        )
            if int(metadata.get("frame_id", -1)) != frame_id:
                raise RuntimeError(
                    f"Frame {frame_id}/{variant}: metadata frame ID does not match"
                )
            if schema_version >= 5 and metadata.get("capture_variant") != variant:
                raise RuntimeError(
                    f"Frame {frame_id}/{variant}: metadata capture variant does not match"
                )
            if schema_version >= 7:
                if metadata.get("capture_operation") != "capture":
                    raise RuntimeError(
                        f"Frame {frame_id}/{variant}: metadata is not a formal capture"
                    )
                if metadata.get("validation_passed") is not True:
                    raise RuntimeError(
                        f"Frame {frame_id}/{variant}: formal validation did not pass"
                    )
                if int(metadata.get("visibility_generation", -1)) < 0:
                    raise RuntimeError(
                        f"Frame {frame_id}/{variant}: visibility generation is invalid"
                    )
                if int(metadata.get("settle_attempts_before_capture", 0)) < 1:
                    raise RuntimeError(
                        f"Frame {frame_id}/{variant}: no successful settle attempt was recorded"
                    )
            if metadata.get("unknown_labels"):
                raise RuntimeError(
                    f"Frame {frame_id}/{variant}: unknown labels "
                    f"{metadata['unknown_labels']}"
                )
            if list(metadata.get("resolution", [])) != [
                expected_shape[1],
                expected_shape[0],
            ]:
                raise RuntimeError(
                    f"Frame {frame_id}/{variant}: metadata resolution does not match"
                )
            if timing is not None:
                require_close(
                    f"Frame {frame_id}/{variant} metadata dataset_time",
                    float(metadata["dataset_time"]),
                    timing.dataset_time_for_frame(frame_id),
                )
    return full_scene_metadata


def validate_states(
    output: Path,
    run_config: dict[str, Any],
    metadata_values: list[dict[str, Any]],
    expected: int,
    timing: CaptureTiming | None,
) -> tuple[list[str], bool]:
    with (output / "motion_state.jsonl").open("r", encoding="utf-8") as stream:
        states = [json.loads(line) for line in stream if line.strip()]
    if len(states) != expected:
        raise RuntimeError(f"motion_state.jsonl contains {len(states)} states, expected {expected}")

    joint_limits = {entry["name"]: entry for entry in run_config.get("joints", [])}
    schema_version = int(run_config.get("schema_version", 1))
    isolated_enabled = bool(
        run_config.get("excavator_only_capture", {}).get("enabled", False)
    )
    front_teeth_enabled = bool(
        run_config.get("front_teeth_only_capture", {}).get("enabled", False)
    )
    expected_variants = {"full_scene"}
    if isolated_enabled:
        expected_variants.add("excavator_only")
    if schema_version >= 6 and front_teeth_enabled:
        expected_variants.add("front_teeth_only")
    for frame_id, (state, metadata) in enumerate(zip(states, metadata_values)):
        if int(state.get("frame_id", -1)) != frame_id:
            raise RuntimeError(f"Frame {frame_id}: motion state frame ID does not match")
        if timing is not None:
            expected_time = timing.dataset_time_for_frame(frame_id)
            require_close(
                f"Frame {frame_id} state dataset_time",
                float(state["dataset_time"]),
                expected_time,
            )
            require_close(
                f"Frame {frame_id} metadata/state timeline_time",
                float(metadata["timeline_time"]),
                float(state["timeline_time"]),
            )
            if int(metadata["physics_step"]) != int(state["physics_step"]):
                raise RuntimeError(f"Frame {frame_id}: metadata/state physics step mismatch")
        if schema_version >= 5:
            receipts = state.get("capture_receipts")
            if not isinstance(receipts, dict) or set(receipts) != expected_variants:
                raise RuntimeError(
                    f"Frame {frame_id}: capture_receipts variants do not match "
                    f"{sorted(expected_variants)}"
                )
            for variant, receipt in receipts.items():
                if int(receipt.get("frame_id", -1)) != frame_id:
                    raise RuntimeError(
                        f"Frame {frame_id}/{variant}: receipt frame ID does not match"
                    )
                if receipt.get("capture_variant") != variant:
                    raise RuntimeError(
                        f"Frame {frame_id}/{variant}: receipt variant does not match"
                    )
                if schema_version >= 7:
                    if receipt.get("capture_operation") != "capture":
                        raise RuntimeError(
                            f"Frame {frame_id}/{variant}: receipt is not a formal capture"
                        )
                    if receipt.get("validation_passed") is not True:
                        raise RuntimeError(
                            f"Frame {frame_id}/{variant}: receipt validation did not pass"
                        )
                    if int(receipt.get("settle_attempts_before_capture", 0)) < 1:
                        raise RuntimeError(
                            f"Frame {frame_id}/{variant}: receipt has no settle attempt"
                        )
            if schema_version >= 7:
                if state.get("frame_committed") is not True:
                    raise RuntimeError(f"Frame {frame_id}: frame transaction was not committed")
                if state.get("end_variant") != "full_scene":
                    raise RuntimeError(
                        f"Frame {frame_id}: frame ended in {state.get('end_variant')!r}"
                    )
                if int(state.get("writer_pending", -1)) != 0:
                    raise RuntimeError(f"Frame {frame_id}: Writer was not idle at frame end")
                probes = state.get("probe_receipts")
                expected_probe_groups = {
                    "full_scene_pre_capture",
                    "full_scene_restore",
                }
                if isolated_enabled:
                    expected_probe_groups.add("excavator_only")
                if front_teeth_enabled:
                    expected_probe_groups.add("front_teeth_only")
                if not isinstance(probes, dict) or set(probes) != expected_probe_groups:
                    raise RuntimeError(
                        f"Frame {frame_id}: probe receipt groups do not match "
                        f"{sorted(expected_probe_groups)}"
                    )
                for group, group_receipts in probes.items():
                    if not isinstance(group_receipts, list) or not group_receipts:
                        raise RuntimeError(
                            f"Frame {frame_id}/{group}: no ProbeReceipt was recorded"
                        )
                    if group_receipts[-1].get("validation_passed") is not True:
                        raise RuntimeError(
                            f"Frame {frame_id}/{group}: final ProbeReceipt did not pass"
                        )
                restore_receipt = probes["full_scene_restore"][-1]
                if restore_receipt.get("capture_variant") != "full_scene":
                    raise RuntimeError(
                        f"Frame {frame_id}: final ProbeReceipt is not full_scene"
                    )
                if int(restore_receipt.get("visibility_generation", -1)) != int(
                    state.get("end_visibility_generation", -2)
                ):
                    raise RuntimeError(
                        f"Frame {frame_id}: final ProbeReceipt generation does not "
                        "match frame-end generation"
                    )
        motion = state["motion"]
        if schema_version >= 3 and run_config.get("motion_enabled"):
            validate_articulation_motion_state(frame_id, motion, run_config, joint_limits)
        if schema_version >= 8 and run_config.get("motion_enabled"):
            validate_root_motion_state(frame_id, motion, run_config)
        for name, target in motion.get("target_degrees", {}).items():
            if name not in joint_limits:
                raise RuntimeError(f"Frame {frame_id}: no limits recorded for joint {name}")
            joint = joint_limits[name]
            if not joint["lower_limit_degrees"] <= target <= joint["upper_limit_degrees"]:
                raise RuntimeError(f"Joint {name} target is outside limits: {target}")

    transforms_by_body: dict[str, list[list[float] | None]] = {}
    for state in states:
        for name, transform in state["motion"].get("body_world_transform", {}).items():
            transforms_by_body.setdefault(name, []).append(transform)
    moving_bodies = sorted(name for name, values in transforms_by_body.items() if changed(values))
    camera_transforms = [state["camera"].get("world_transform") for state in states]
    camera_moved = changed(camera_transforms)

    capture_mode = run_config.get("capture_mode", "motion")
    if capture_mode == "static":
        if moving_bodies or camera_moved:
            raise RuntimeError(
                f"Static capture changed scene transforms: bodies={moving_bodies}, camera={camera_moved}"
            )
    elif run_config.get("motion_enabled") and expected > 1:
        if not moving_bodies:
            raise RuntimeError("No controlled body world transform changed across motion capture")
        if schema_version >= 8:
            trajectory = run_config.get("trajectory", {})
            root_changes = bool(
                trajectory.get("root_position_changes")
                or trajectory.get("root_orientation_changes")
            )
            if root_changes and "root" not in moving_bodies:
                raise RuntimeError(
                    "Trajectory changes root pose, but the root body transform did not move"
                )
    return moving_bodies, camera_moved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--expected-frames", type=int, default=None)
    args = parser.parse_args()

    output = Path(args.output)
    mapping = SemanticMapping(args.mapping)
    run_config = load_json(output / "run_config.json")
    expected = int(args.expected_frames or run_config.get("frames", 50))
    schema_version = int(run_config.get("schema_version", 1))
    timing = validate_manifest_v2(run_config, expected) if schema_version >= 2 else None
    if schema_version >= 3:
        validate_manifest_v3(run_config)
    if schema_version >= 9:
        validate_manifest_v9(run_config)
    elif schema_version >= 8:
        validate_manifest_v8(run_config)
    metadata_values = validate_frame_files(
        output=output,
        mapping=mapping,
        run_config=run_config,
        expected=expected,
        timing=timing,
    )
    moving_bodies, camera_moved = validate_states(
        output=output,
        run_config=run_config,
        metadata_values=metadata_values,
        expected=expected,
        timing=timing,
    )
    if schema_version >= 7:
        staging_root = output / ".frame_staging"
        if staging_root.exists() and any(staging_root.rglob("*")):
            raise RuntimeError(
                f"Committed dataset still contains frame staging artifacts: {staging_root}"
            )

    print(
        f"[validation] PASS: {expected} frames, schema={schema_version}, "
        f"semantic mapping consistent, moving bodies={moving_bodies}, camera moved={camera_moved}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
