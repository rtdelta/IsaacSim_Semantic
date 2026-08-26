"""Strict schema-v6 configuration loader independent from Isaac Sim."""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .errors import ConfigurationError
from .models import AcquisitionKind, jsonable, stable_hash


SCHEMA_VERSION = 6
_SENSOR_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{label} must be an object")
    return dict(value)


def _unknown(raw: dict[str, Any], allowed: set[str], label: str) -> None:
    values = sorted(set(raw) - allowed)
    if values:
        raise ConfigurationError(f"Unknown {label} field(s): {', '.join(values)}")


def _string(raw: dict[str, Any], name: str, label: str, *, default: str | None = None) -> str:
    value = raw.get(name, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{label}.{name} must be a non-empty string")
    return value.strip()


def _positive_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ConfigurationError(f"{label} must be a positive number")
    return float(value)


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigurationError(f"{label} must be a positive integer")
    return int(value)


def _absolute_prim_path(value: str, label: str) -> str:
    if not value.startswith("/") or value == "/" or "//" in value:
        raise ConfigurationError(f"{label} must be an absolute USD prim path")
    return value


def _resolve_reference(value: str | None, base_dir: Path) -> str | None:
    if value is None:
        return None
    if value.startswith("/") or _WINDOWS_ABSOLUTE_RE.match(value) or "://" in value:
        return value
    return str((base_dir / value).resolve())


@dataclass(frozen=True)
class MotionConfig:
    driver: str
    trajectory: str | None
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SceneConfig:
    usd: str
    physics_hz: int
    mapping: str | None = None
    motion: MotionConfig | None = None
    state_prim_paths: tuple[str, ...] = ()
    pre_roll_steps: int = 0


@dataclass(frozen=True)
class RenderGroupConfig:
    group_id: str
    kind: str
    profile: str | None
    execution: str
    multi_gpu: bool
    rt_subframes: int
    warmup_frames: int
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SensorSourceConfig:
    mode: str
    prim_path: str | None = None
    parent_prim: str | None = None
    prim_name: str | None = None
    config: str | None = None
    usd_path: str | None = None
    variant: str | dict[str, str] | None = None

    @property
    def resolved_prim_path(self) -> str:
        if self.prim_path:
            return self.prim_path
        if self.parent_prim and self.prim_name:
            return self.parent_prim.rstrip("/") + "/" + self.prim_name
        raise ConfigurationError("Sensor source does not resolve to a prim path")


@dataclass(frozen=True)
class SensorClockConfig:
    hz: float
    phase_seconds: float
    acquisition: AcquisitionKind


@dataclass(frozen=True)
class CalibrationConfig:
    policy: str
    profile: str | None = None
    expected_model: str | None = None
    expected_hash: str | None = None
    model: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SensorOutputConfig:
    sink: str
    required: bool
    folder: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SensorConfig:
    sensor_id: str
    sensor_type: str
    enabled: bool
    source: SensorSourceConfig
    render_group: str
    clock: SensorClockConfig
    modalities: tuple[str, ...]
    resolution: tuple[int, int] | None
    calibration: CalibrationConfig
    output: SensorOutputConfig
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VariantConfig:
    variant_id: str
    visibility: dict[str, str] = field(default_factory=dict)
    include_paths: tuple[str, ...] = ()
    modalities_by_sensor: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def modalities_for(self, sensor: SensorConfig) -> tuple[str, ...]:
        """Return the payload modalities committed for this sensor and variant."""

        return self.modalities_by_sensor.get(sensor.sensor_id, sensor.modalities)


@dataclass(frozen=True)
class SynchronizationGroupConfig:
    group_id: str
    sensor_ids: tuple[str, ...]
    commit_policy: str


@dataclass(frozen=True)
class CaptureConfig:
    frames: int
    base_hz: float
    capture_initial_frame: bool
    variant_execution: str
    variants: tuple[VariantConfig, ...]
    synchronization_groups: tuple[SynchronizationGroupConfig, ...]


@dataclass(frozen=True)
class RuntimeConfig:
    segment_frames: int
    resume: bool
    heartbeat_seconds: float
    startup_timeout_seconds: float
    render_timeout_seconds: float
    shutdown_timeout_seconds: float
    max_worker_restarts: int
    poll_seconds: float
    worker_command: tuple[str, ...]


@dataclass(frozen=True)
class RunConfig:
    source_path: Path
    schema_version: int
    run_id: str
    output: str
    scene: SceneConfig
    render_groups: dict[str, RenderGroupConfig]
    driver_plugins: dict[str, str]
    sensors: tuple[SensorConfig, ...]
    capture: CaptureConfig
    runtime: RuntimeConfig
    fingerprint: str

    @property
    def enabled_sensors(self) -> tuple[SensorConfig, ...]:
        return tuple(sensor for sensor in self.sensors if sensor.enabled)

    def sensor(self, sensor_id: str) -> SensorConfig:
        for sensor in self.sensors:
            if sensor.sensor_id == sensor_id:
                return sensor
        raise KeyError(sensor_id)

    def variant(self, variant_id: str) -> VariantConfig:
        for variant in self.capture.variants:
            if variant.variant_id == variant_id:
                return variant
        raise KeyError(variant_id)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source_path"] = str(self.source_path)
        return jsonable(payload)


def _load_scene(raw: dict[str, Any], base_dir: Path) -> SceneConfig:
    _unknown(
        raw,
        {"usd", "physics_hz", "mapping", "motion", "state_prim_paths", "pre_roll_steps"},
        "scene",
    )
    usd = _resolve_reference(_string(raw, "usd", "scene"), base_dir)
    mapping_raw = raw.get("mapping")
    if mapping_raw is not None and not isinstance(mapping_raw, str):
        raise ConfigurationError("scene.mapping must be a string or null")
    motion_raw = raw.get("motion")
    motion: MotionConfig | None = None
    if motion_raw is not None:
        item = _object(motion_raw, "scene.motion")
        _unknown(item, {"driver", "trajectory", "settings"}, "scene.motion")
        driver = _string(item, "driver", "scene.motion")
        if ":" not in driver:
            raise ConfigurationError("scene.motion.driver must be module.path:ClassName")
        trajectory = item.get("trajectory")
        if trajectory is not None and not isinstance(trajectory, str):
            raise ConfigurationError("scene.motion.trajectory must be a string or null")
        motion = MotionConfig(
            driver=driver,
            trajectory=_resolve_reference(trajectory, base_dir),
            settings=_object(item.get("settings", {}), "scene.motion.settings"),
        )
    state_paths = raw.get("state_prim_paths", [])
    if not isinstance(state_paths, list) or any(not isinstance(item, str) for item in state_paths):
        raise ConfigurationError("scene.state_prim_paths must be a list of prim paths")
    state_paths = tuple(_absolute_prim_path(item, "scene.state_prim_paths") for item in state_paths)
    pre_roll = raw.get("pre_roll_steps", 0)
    if isinstance(pre_roll, bool) or not isinstance(pre_roll, int) or pre_roll < 0:
        raise ConfigurationError("scene.pre_roll_steps must be a non-negative integer")
    return SceneConfig(
        usd=str(usd),
        physics_hz=_positive_int(raw.get("physics_hz"), "scene.physics_hz"),
        mapping=_resolve_reference(mapping_raw, base_dir),
        motion=motion,
        state_prim_paths=state_paths,
        pre_roll_steps=pre_roll,
    )


def _load_render_groups(raw: dict[str, Any], base_dir: Path) -> dict[str, RenderGroupConfig]:
    if not raw:
        raise ConfigurationError("render_groups must contain at least one group")
    result: dict[str, RenderGroupConfig] = {}
    for group_id, value in raw.items():
        if not _SENSOR_ID_RE.match(group_id):
            raise ConfigurationError(f"Invalid render group ID: {group_id!r}")
        item = _object(value, f"render_groups.{group_id}")
        _unknown(
            item,
            {
                "kind", "profile", "execution", "multi_gpu", "rt_subframes",
                "warmup_frames", "settings",
            },
            f"render_groups.{group_id}",
        )
        kind = _string(item, "kind", f"render_groups.{group_id}")
        if kind not in {"camera_rtx", "rtx_sensor", "mixed_rtx"}:
            raise ConfigurationError(f"Unsupported render group kind: {kind}")
        execution = item.get("execution", "serial")
        if execution not in {"serial", "batched"}:
            raise ConfigurationError(f"Unsupported render group execution: {execution}")
        multi_gpu = item.get("multi_gpu", False)
        if not isinstance(multi_gpu, bool):
            raise ConfigurationError(f"render_groups.{group_id}.multi_gpu must be boolean")
        profile = item.get("profile")
        if profile is not None and not isinstance(profile, str):
            raise ConfigurationError(f"render_groups.{group_id}.profile must be a string or null")
        settings = _object(item.get("settings", {}), f"render_groups.{group_id}.settings")
        result[group_id] = RenderGroupConfig(
            group_id=group_id,
            kind=kind,
            profile=_resolve_reference(profile, base_dir),
            execution=execution,
            multi_gpu=multi_gpu,
            rt_subframes=_positive_int(item.get("rt_subframes", 1), f"render_groups.{group_id}.rt_subframes"),
            warmup_frames=int(item.get("warmup_frames", 0)),
            settings=settings,
        )
        if result[group_id].warmup_frames < 0:
            raise ConfigurationError(f"render_groups.{group_id}.warmup_frames must be non-negative")
    return result


def _load_source(raw: dict[str, Any], label: str, base_dir: Path) -> SensorSourceConfig:
    _unknown(
        raw,
        {"mode", "prim_path", "parent_prim", "prim_name", "config", "usd_path", "variant"},
        f"{label}.source",
    )
    mode = _string(raw, "mode", f"{label}.source")
    if mode not in {"existing_prim", "create"}:
        raise ConfigurationError(f"{label}.source.mode must be existing_prim or create")
    if mode == "existing_prim":
        prim_path = _absolute_prim_path(
            _string(raw, "prim_path", f"{label}.source"), f"{label}.source.prim_path"
        )
        return SensorSourceConfig(mode=mode, prim_path=prim_path)
    parent = _absolute_prim_path(
        _string(raw, "parent_prim", f"{label}.source"), f"{label}.source.parent_prim"
    )
    prim_name = _string(raw, "prim_name", f"{label}.source")
    if "/" in prim_name:
        raise ConfigurationError(f"{label}.source.prim_name must be one USD name")
    config = raw.get("config")
    usd_path = raw.get("usd_path")
    if config is not None and not isinstance(config, str):
        raise ConfigurationError(f"{label}.source.config must be a string or null")
    if usd_path is not None and not isinstance(usd_path, str):
        raise ConfigurationError(f"{label}.source.usd_path must be a string or null")
    if config and usd_path:
        raise ConfigurationError(f"{label}.source.config and usd_path are mutually exclusive")
    variant = raw.get("variant")
    if variant is not None and not isinstance(variant, (str, dict)):
        raise ConfigurationError(f"{label}.source.variant must be a string, object, or null")
    if isinstance(variant, dict) and any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in variant.items()
    ):
        raise ConfigurationError(f"{label}.source.variant keys and values must be strings")
    return SensorSourceConfig(
        mode=mode,
        parent_prim=parent,
        prim_name=prim_name,
        config=config,
        usd_path=_resolve_reference(usd_path, base_dir),
        variant=variant,
    )


def _load_calibration(raw: dict[str, Any], label: str, base_dir: Path) -> CalibrationConfig:
    _unknown(
        raw,
        {"policy", "profile", "expected_model", "expected_hash", "model", "attributes"},
        f"{label}.calibration",
    )
    policy = raw.get("policy", "read_from_prim")
    if policy not in {"read_from_prim", "read_and_validate", "from_profile", "inline", "explicit_override"}:
        raise ConfigurationError(f"Unsupported {label}.calibration.policy: {policy}")
    profile = raw.get("profile")
    if profile is not None and not isinstance(profile, str):
        raise ConfigurationError(f"{label}.calibration.profile must be a string or null")
    attributes = _object(raw.get("attributes", {}), f"{label}.calibration.attributes")
    for key in ("expected_model", "expected_hash", "model"):
        if raw.get(key) is not None and not isinstance(raw[key], str):
            raise ConfigurationError(f"{label}.calibration.{key} must be a string or null")
    if policy == "from_profile" and not profile:
        raise ConfigurationError(f"{label}.calibration.profile is required for from_profile")
    if policy == "inline" and not attributes:
        raise ConfigurationError(f"{label}.calibration.attributes is required for inline")
    return CalibrationConfig(
        policy=policy,
        profile=_resolve_reference(profile, base_dir),
        expected_model=raw.get("expected_model"),
        expected_hash=raw.get("expected_hash"),
        model=raw.get("model"),
        attributes=attributes,
    )


def _load_sensor(raw: dict[str, Any], index: int, base_dir: Path) -> SensorConfig:
    label = f"sensors[{index}]"
    _unknown(
        raw,
        {
            "id", "type", "enabled", "source", "render_group", "clock", "modalities",
            "resolution", "calibration", "output", "settings",
        },
        label,
    )
    sensor_id = _string(raw, "id", label)
    if not _SENSOR_ID_RE.match(sensor_id):
        raise ConfigurationError(f"Invalid sensor ID: {sensor_id!r}")
    sensor_type = _string(raw, "type", label)
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigurationError(f"{label}.enabled must be boolean")
    source = _load_source(_object(raw.get("source"), f"{label}.source"), label, base_dir)
    clock_raw = _object(raw.get("clock"), f"{label}.clock")
    _unknown(clock_raw, {"hz", "phase_seconds", "acquisition"}, f"{label}.clock")
    acquisition_raw = clock_raw.get("acquisition", "snapshot")
    try:
        acquisition = AcquisitionKind(acquisition_raw)
    except ValueError as exc:
        raise ConfigurationError(f"Unsupported {label}.clock.acquisition: {acquisition_raw}") from exc
    phase = clock_raw.get("phase_seconds", 0.0)
    if isinstance(phase, bool) or not isinstance(phase, (int, float)) or phase < 0:
        raise ConfigurationError(f"{label}.clock.phase_seconds must be non-negative")
    modalities = raw.get("modalities")
    if not isinstance(modalities, list) or not modalities or any(
        not isinstance(item, str) or not item.strip() for item in modalities
    ):
        raise ConfigurationError(f"{label}.modalities must be a non-empty list of strings")
    if len(modalities) != len(set(modalities)):
        raise ConfigurationError(f"{label}.modalities contains duplicates")
    resolution_raw = raw.get("resolution")
    resolution: tuple[int, int] | None = None
    if resolution_raw is not None:
        if (
            not isinstance(resolution_raw, list)
            or len(resolution_raw) != 2
            or any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in resolution_raw)
        ):
            raise ConfigurationError(f"{label}.resolution must be [width, height]")
        resolution = (resolution_raw[0], resolution_raw[1])
    if sensor_type.startswith("camera.") and resolution is None:
        raise ConfigurationError(f"{label}.resolution is required for camera sensors")
    calibration = _load_calibration(
        _object(raw.get("calibration", {}), f"{label}.calibration"), label, base_dir
    )
    output_raw = _object(raw.get("output", {}), f"{label}.output")
    _unknown(output_raw, {"sink", "required", "folder", "settings"}, f"{label}.output")
    required = output_raw.get("required", True)
    if not isinstance(required, bool):
        raise ConfigurationError(f"{label}.output.required must be boolean")
    folder = output_raw.get("folder")
    if folder is not None:
        if not isinstance(folder, str) or not folder.strip() or Path(folder).is_absolute() or ".." in Path(folder).parts:
            raise ConfigurationError(f"{label}.output.folder must be a safe relative path")
    sink = output_raw.get("sink", "filesystem")
    if sink != "filesystem":
        raise ConfigurationError(f"{label}.output.sink currently supports only filesystem")
    return SensorConfig(
        sensor_id=sensor_id,
        sensor_type=sensor_type,
        enabled=enabled,
        source=source,
        render_group=_string(raw, "render_group", label),
        clock=SensorClockConfig(
            hz=_positive_number(clock_raw.get("hz"), f"{label}.clock.hz"),
            phase_seconds=float(phase),
            acquisition=acquisition,
        ),
        modalities=tuple(modalities),
        resolution=resolution,
        calibration=calibration,
        output=SensorOutputConfig(
            sink=sink,
            required=required,
            folder=folder,
            settings=_object(output_raw.get("settings", {}), f"{label}.output.settings"),
        ),
        settings=_object(raw.get("settings", {}), f"{label}.settings"),
    )


def _load_capture(raw: dict[str, Any]) -> CaptureConfig:
    _unknown(
        raw,
        {"frames", "base_hz", "capture_initial_frame", "variant_execution", "variants", "synchronization_groups"},
        "capture",
    )
    execution = raw.get("variant_execution", "variant_major")
    if execution not in {"variant_major", "frame_major"}:
        raise ConfigurationError("capture.variant_execution must be variant_major or frame_major")
    capture_initial_frame = raw.get("capture_initial_frame", True)
    if not isinstance(capture_initial_frame, bool):
        raise ConfigurationError("capture.capture_initial_frame must be boolean")
    variants_raw = raw.get("variants", [{"id": "full_scene", "visibility": {}}])
    if not isinstance(variants_raw, list) or not variants_raw:
        raise ConfigurationError("capture.variants must be a non-empty list")
    variants: list[VariantConfig] = []
    for index, value in enumerate(variants_raw):
        item = _object(value, f"capture.variants[{index}]")
        _unknown(
            item,
            {"id", "visibility", "include_paths", "modalities_by_sensor"},
            f"capture.variants[{index}]",
        )
        variant_id = _string(item, "id", f"capture.variants[{index}]")
        if not _SENSOR_ID_RE.match(variant_id):
            raise ConfigurationError(f"Invalid capture variant ID: {variant_id!r}")
        visibility = _object(item.get("visibility", {}), f"capture.variants[{index}].visibility")
        for path, state in visibility.items():
            _absolute_prim_path(path, f"capture.variants[{index}].visibility")
            if state not in {"inherited", "invisible"}:
                raise ConfigurationError(f"Visibility for {path} must be inherited or invisible")
        include_paths_raw = item.get("include_paths", [])
        if (
            not isinstance(include_paths_raw, list)
            or any(not isinstance(path, str) for path in include_paths_raw)
        ):
            raise ConfigurationError(
                f"capture.variants[{index}].include_paths must be a list of prim paths"
            )
        include_paths = tuple(
            _absolute_prim_path(path, f"capture.variants[{index}].include_paths")
            for path in include_paths_raw
        )
        if len(include_paths) != len(set(include_paths)):
            raise ConfigurationError(
                f"capture.variants[{index}].include_paths contains duplicates"
            )
        modalities_raw = _object(
            item.get("modalities_by_sensor", {}),
            f"capture.variants[{index}].modalities_by_sensor",
        )
        modalities_by_sensor: dict[str, tuple[str, ...]] = {}
        for sensor_id, values in modalities_raw.items():
            if not isinstance(sensor_id, str) or not _SENSOR_ID_RE.match(sensor_id):
                raise ConfigurationError(
                    f"capture.variants[{index}].modalities_by_sensor has invalid sensor ID"
                )
            if (
                not isinstance(values, list)
                or not values
                or any(not isinstance(value, str) or not value.strip() for value in values)
            ):
                raise ConfigurationError(
                    f"capture.variants[{index}].modalities_by_sensor.{sensor_id} "
                    "must be a non-empty list of strings"
                )
            normalized = tuple(value.strip() for value in values)
            if len(normalized) != len(set(normalized)):
                raise ConfigurationError(
                    f"capture.variants[{index}].modalities_by_sensor.{sensor_id} contains duplicates"
                )
            modalities_by_sensor[sensor_id] = normalized
        variants.append(
            VariantConfig(
                variant_id=variant_id,
                visibility=visibility,
                include_paths=include_paths,
                modalities_by_sensor=modalities_by_sensor,
            )
        )
    if len({item.variant_id for item in variants}) != len(variants):
        raise ConfigurationError("capture.variants contains duplicate IDs")
    groups_raw = raw.get("synchronization_groups", [])
    if not isinstance(groups_raw, list):
        raise ConfigurationError("capture.synchronization_groups must be a list")
    groups: list[SynchronizationGroupConfig] = []
    for index, value in enumerate(groups_raw):
        item = _object(value, f"capture.synchronization_groups[{index}]")
        _unknown(item, {"id", "sensor_ids", "commit_policy"}, f"capture.synchronization_groups[{index}]")
        sensor_ids = item.get("sensor_ids")
        if not isinstance(sensor_ids, list) or not sensor_ids or any(not isinstance(v, str) for v in sensor_ids):
            raise ConfigurationError(f"capture.synchronization_groups[{index}].sensor_ids must be non-empty")
        if len(sensor_ids) != len(set(sensor_ids)):
            raise ConfigurationError(
                f"capture.synchronization_groups[{index}].sensor_ids contains duplicates"
            )
        policy = item.get("commit_policy", "all_or_nothing")
        if policy not in {"all_or_nothing", "best_effort"}:
            raise ConfigurationError(f"Unsupported synchronization commit policy: {policy}")
        groups.append(
            SynchronizationGroupConfig(
                group_id=_string(item, "id", f"capture.synchronization_groups[{index}]"),
                sensor_ids=tuple(sensor_ids),
                commit_policy=policy,
            )
        )
    return CaptureConfig(
        frames=_positive_int(raw.get("frames"), "capture.frames"),
        base_hz=_positive_number(raw.get("base_hz"), "capture.base_hz"),
        capture_initial_frame=capture_initial_frame,
        variant_execution=execution,
        variants=tuple(variants),
        synchronization_groups=tuple(groups),
    )


def _load_runtime(raw: dict[str, Any]) -> RuntimeConfig:
    _unknown(
        raw,
        {
            "segment_frames", "resume", "heartbeat_seconds", "startup_timeout_seconds",
            "render_timeout_seconds", "shutdown_timeout_seconds", "max_worker_restarts",
            "poll_seconds", "worker_command",
        },
        "runtime",
    )
    resume = raw.get("resume", True)
    if not isinstance(resume, bool):
        raise ConfigurationError("runtime.resume must be boolean")
    restarts = raw.get("max_worker_restarts", 3)
    if isinstance(restarts, bool) or not isinstance(restarts, int) or restarts < 0:
        raise ConfigurationError("runtime.max_worker_restarts must be non-negative")
    worker_command = raw.get("worker_command", [])
    if not isinstance(worker_command, list) or any(not isinstance(item, str) or not item for item in worker_command):
        raise ConfigurationError("runtime.worker_command must be a list of command arguments")
    return RuntimeConfig(
        segment_frames=_positive_int(raw.get("segment_frames", 500), "runtime.segment_frames"),
        resume=resume,
        heartbeat_seconds=_positive_number(raw.get("heartbeat_seconds", 5), "runtime.heartbeat_seconds"),
        startup_timeout_seconds=_positive_number(raw.get("startup_timeout_seconds", 300), "runtime.startup_timeout_seconds"),
        render_timeout_seconds=_positive_number(raw.get("render_timeout_seconds", 180), "runtime.render_timeout_seconds"),
        shutdown_timeout_seconds=_positive_number(raw.get("shutdown_timeout_seconds", 30), "runtime.shutdown_timeout_seconds"),
        max_worker_restarts=restarts,
        poll_seconds=_positive_number(raw.get("poll_seconds", 1), "runtime.poll_seconds"),
        worker_command=tuple(worker_command),
    )


def _validate_cross_references(config: RunConfig) -> None:
    sensor_ids = [sensor.sensor_id for sensor in config.sensors]
    if len(sensor_ids) != len(set(sensor_ids)):
        raise ConfigurationError("sensors contains duplicate IDs")
    enabled_ids = {sensor.sensor_id for sensor in config.enabled_sensors}
    if not enabled_ids:
        raise ConfigurationError("At least one sensor must be enabled")
    for sensor in config.enabled_sensors:
        if sensor.render_group not in config.render_groups:
            raise ConfigurationError(
                f"Sensor {sensor.sensor_id} references unknown render group {sensor.render_group}"
            )
        period = config.scene.physics_hz / sensor.clock.hz
        if not math.isclose(period, round(period), rel_tol=0.0, abs_tol=1e-9):
            raise ConfigurationError(
                f"Sensor {sensor.sensor_id} frequency {sensor.clock.hz:g} Hz does not divide "
                f"physics_hz={config.scene.physics_hz}"
            )
        base_ratio = config.capture.base_hz / sensor.clock.hz
        if not math.isclose(base_ratio, round(base_ratio), rel_tol=0.0, abs_tol=1e-9):
            raise ConfigurationError(
                f"Sensor {sensor.sensor_id} frequency must divide capture.base_hz; "
                f"otherwise scheduled samples would be skipped"
            )
        if sensor.sensor_type.startswith("camera.") and sensor.clock.acquisition is not AcquisitionKind.SNAPSHOT:
            raise ConfigurationError(f"Camera {sensor.sensor_id} must use snapshot acquisition")
        if sensor.sensor_type.startswith("lidar.rtx") and sensor.clock.acquisition is not AcquisitionKind.INTERVAL:
            raise ConfigurationError(f"RTX LiDAR {sensor.sensor_id} must use interval acquisition")
        group = config.render_groups[sensor.render_group]
        if sensor.sensor_type.startswith("camera.") and group.kind not in {"camera_rtx", "mixed_rtx"}:
            raise ConfigurationError(f"Camera {sensor.sensor_id} requires a camera_rtx render group")
        if sensor.sensor_type.startswith("lidar.") and group.kind not in {"rtx_sensor", "mixed_rtx"}:
            raise ConfigurationError(f"LiDAR {sensor.sensor_id} requires an rtx_sensor render group")
    base_period = config.scene.physics_hz / config.capture.base_hz
    if not math.isclose(base_period, round(base_period), rel_tol=0.0, abs_tol=1e-9):
        raise ConfigurationError("capture.base_hz must divide scene.physics_hz")
    base_steps = int(round(base_period))
    for sensor in config.enabled_sensors:
        phase_steps = sensor.clock.phase_seconds * config.scene.physics_hz
        if not math.isclose(phase_steps, round(phase_steps), rel_tol=0.0, abs_tol=1e-9):
            raise ConfigurationError(
                f"Sensor {sensor.sensor_id} phase_seconds must align to a physics step"
            )
        if int(round(phase_steps)) % base_steps:
            raise ConfigurationError(
                f"Sensor {sensor.sensor_id} phase_seconds must align to the capture base grid"
            )
    folders = [
        sensor.output.folder or f"sensors/{sensor.sensor_id}"
        for sensor in config.enabled_sensors
    ]
    if len(folders) != len(set(folders)):
        raise ConfigurationError("Enabled sensors must use distinct output folders")
    for variant in config.capture.variants:
        for sensor_id, modalities in variant.modalities_by_sensor.items():
            if sensor_id not in enabled_ids:
                raise ConfigurationError(
                    f"Variant {variant.variant_id} references disabled/unknown sensor {sensor_id}"
                )
            configured = set(config.sensor(sensor_id).modalities)
            unsupported = sorted(set(modalities) - configured)
            if unsupported:
                raise ConfigurationError(
                    f"Variant {variant.variant_id} requests modalities not configured for "
                    f"sensor {sensor_id}: {', '.join(unsupported)}"
                )
    group_ids: set[str] = set()
    members: set[str] = set()
    for group in config.capture.synchronization_groups:
        if group.group_id in group_ids:
            raise ConfigurationError(f"Duplicate synchronization group ID: {group.group_id}")
        group_ids.add(group.group_id)
        for sensor_id in group.sensor_ids:
            if sensor_id not in enabled_ids:
                raise ConfigurationError(
                    f"Synchronization group {group.group_id} references disabled/unknown sensor {sensor_id}"
                )
            if sensor_id in members:
                raise ConfigurationError(f"Sensor {sensor_id} belongs to more than one synchronization group")
            members.add(sensor_id)
            if config.sensor(sensor_id).clock.acquisition is not AcquisitionKind.SNAPSHOT:
                raise ConfigurationError(
                    f"Synchronization group {group.group_id} may only contain snapshot sensors"
                )
        clocks = {
            (
                config.sensor(sensor_id).clock.hz,
                config.sensor(sensor_id).clock.phase_seconds,
            )
            for sensor_id in group.sensor_ids
        }
        if len(clocks) != 1:
            raise ConfigurationError(
                f"Synchronization group {group.group_id} sensors must have identical hz and phase_seconds"
            )
    if (
        config.capture.variant_execution == "frame_major"
        and len(config.capture.variants) > 1
        and any(
            sensor.clock.acquisition is AcquisitionKind.INTERVAL
            for sensor in config.enabled_sensors
        )
    ):
        raise ConfigurationError(
            "frame_major with multiple variants cannot produce independent interval sensors; "
            "use variant_major"
        )


def load_run_config(path: str | Path) -> RunConfig:
    source_path = Path(path).resolve()
    try:
        raw = json.loads(source_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Configuration file does not exist: {source_path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Invalid JSON configuration: {exc}") from exc
    raw = _object(raw, "root")
    _unknown(
        raw,
        {"schema_version", "run_id", "output", "scene", "render_groups", "drivers", "sensors", "capture", "runtime"},
        "root",
    )
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ConfigurationError(
            f"schema_version must be {SCHEMA_VERSION}, got {raw.get('schema_version')!r}"
        )
    run_id = _string(raw, "run_id", "root")
    if not _SENSOR_ID_RE.match(run_id):
        raise ConfigurationError(f"Invalid run_id: {run_id!r}")
    output = _resolve_reference(_string(raw, "output", "root"), source_path.parent)
    sensors_raw = raw.get("sensors")
    if not isinstance(sensors_raw, list) or not sensors_raw:
        raise ConfigurationError("sensors must be a non-empty list")
    scene = _load_scene(_object(raw.get("scene"), "scene"), source_path.parent)
    render_groups = _load_render_groups(
        _object(raw.get("render_groups"), "render_groups"), source_path.parent
    )
    drivers = _object(raw.get("drivers", {}), "drivers")
    for sensor_type, class_path in drivers.items():
        if not _SENSOR_ID_RE.match(sensor_type):
            raise ConfigurationError(f"Invalid driver sensor type: {sensor_type!r}")
        if not isinstance(class_path, str) or ":" not in class_path:
            raise ConfigurationError(
                f"drivers.{sensor_type} must be a 'module.path:ClassName' string"
            )
    sensors = tuple(
        _load_sensor(_object(value, f"sensors[{index}]"), index, source_path.parent)
        for index, value in enumerate(sensors_raw)
    )
    capture = _load_capture(_object(raw.get("capture"), "capture"))
    runtime = _load_runtime(_object(raw.get("runtime", {}), "runtime"))
    fingerprint_payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "output": output,
        "scene": scene,
        "render_groups": render_groups,
        "drivers": drivers,
        "sensors": sensors,
        "capture": capture,
    }
    config = RunConfig(
        source_path=source_path,
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
        output=str(output),
        scene=scene,
        render_groups=render_groups,
        driver_plugins=dict(drivers),
        sensors=sensors,
        capture=capture,
        runtime=runtime,
        fingerprint=stable_hash(jsonable(fingerprint_payload)),
    )
    _validate_cross_references(config)
    return config
