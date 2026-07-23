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
    if int(writer.get("completed", -1)) != expected:
        raise RuntimeError(
            f"Writer completed {writer.get('completed')} frames, expected {expected}"
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
    save_runtime_ids = bool(run_config.get("save_runtime_ids", True))
    required_patterns = {
        "rgb": "rgb_*.png",
        "semantic_id": "semantic_id_*.npy",
        "semantic_color": "semantic_color_*.png",
        "metadata": "frame_*.json",
    }
    if save_runtime_ids:
        required_patterns["semantic_runtime_id"] = "semantic_runtime_id_*.npy"
    for folder, pattern in required_patterns.items():
        count = len(list((output / folder).glob(pattern)))
        if count != expected:
            raise RuntimeError(f"{folder} contains {count} frame files, expected {expected}")

    metadata_values: list[dict[str, Any]] = []
    for frame_id in range(expected):
        frame_name = f"{frame_id:04d}"
        dataset_ids = np.load(output / "semantic_id" / f"semantic_id_{frame_name}.npy")
        if dataset_ids.shape != expected_shape or dataset_ids.dtype != np.uint16:
            raise RuntimeError(
                f"Frame {frame_id}: invalid semantic ID array {dataset_ids.shape} {dataset_ids.dtype}"
            )
        unknown_ids = set(int(value) for value in np.unique(dataset_ids)) - valid_ids
        if unknown_ids:
            raise RuntimeError(f"Frame {frame_id}: undefined semantic IDs {sorted(unknown_ids)}")
        saved_color = np.asarray(
            Image.open(output / "semantic_color" / f"semantic_color_{frame_name}.png").convert("RGB")
        )
        if not np.array_equal(saved_color, mapping.colorize(dataset_ids)):
            raise RuntimeError(f"Frame {frame_id}: semantic color PNG does not match semantic ID NPY")
        with Image.open(output / "rgb" / f"rgb_{frame_name}.png") as rgb_image:
            if rgb_image.size != (expected_shape[1], expected_shape[0]):
                raise RuntimeError(f"Frame {frame_id}: RGB size is {rgb_image.size}")

        metadata = load_json(output / "metadata" / f"frame_{frame_name}.json")
        metadata_values.append(metadata)
        if int(metadata.get("frame_id", -1)) != frame_id:
            raise RuntimeError(f"Frame {frame_id}: metadata frame ID does not match")
        if metadata.get("unknown_labels"):
            raise RuntimeError(f"Frame {frame_id}: unknown labels {metadata['unknown_labels']}")
        if list(metadata.get("resolution", [])) != [expected_shape[1], expected_shape[0]]:
            raise RuntimeError(f"Frame {frame_id}: metadata resolution does not match")
        if timing is not None:
            require_close(
                f"Frame {frame_id} metadata dataset_time",
                float(metadata["dataset_time"]),
                timing.dataset_time_for_frame(frame_id),
            )
    return metadata_values


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
        motion = state["motion"]
        if schema_version >= 3 and run_config.get("motion_enabled"):
            validate_articulation_motion_state(frame_id, motion, run_config, joint_limits)
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

    print(
        f"[validation] PASS: {expected} frames, schema={schema_version}, "
        f"semantic mapping consistent, moving bodies={moving_bodies}, camera moved={camera_moved}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
