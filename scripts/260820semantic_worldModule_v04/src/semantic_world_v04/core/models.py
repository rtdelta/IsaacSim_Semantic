"""Versioned pure-Python domain models.

All from_dict methods reject unknown fields. This catches configuration typos
before a long-running headless capture starts.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from .errors import SchemaError
from .serde import (
    expect_bool,
    expect_int,
    expect_list,
    expect_mapping,
    expect_number,
    expect_string,
    json_object,
    strict_keys,
    string_dict,
    string_list,
    to_data,
)
from .sensor_models import RigDefinition

SCHEMA_VERSION = 2
COMPATIBLE_SCHEMA_VERSIONS = {1, SCHEMA_VERSION}


def _schema_version(data: Mapping[str, Any], path: str) -> int:
    version = expect_int(data.get("schema_version", SCHEMA_VERSION), f"{path}.schema_version")
    if version not in COMPATIBLE_SCHEMA_VERSIONS:
        raise SchemaError(
            f"unsupported schema_version {version}; supported versions are "
            f"{sorted(COMPATIBLE_SCHEMA_VERSIONS)}",
            f"{path}.schema_version",
        )
    return version


@dataclass
class StageReference:
    usd_path: str
    load_payloads: bool = True
    meters_per_unit_override: Optional[float] = None

    @classmethod
    def from_dict(cls, value: Any, path: str = "stage") -> "StageReference":
        data = expect_mapping(value, path)
        strict_keys(
            data,
            allowed={"usd_path", "load_payloads", "meters_per_unit_override"},
            required={"usd_path"},
            path=path,
        )
        meters = data.get("meters_per_unit_override")
        return cls(
            usd_path=expect_string(data["usd_path"], f"{path}.usd_path"),
            load_payloads=expect_bool(data.get("load_payloads", True), f"{path}.load_payloads"),
            meters_per_unit_override=(
                None if meters is None else expect_number(meters, f"{path}.meters_per_unit_override")
            ),
        )


@dataclass
class SensorDefinition:
    sensor_id: str
    plugin: str
    prim_path: str
    enabled: bool = True
    stage_parameters: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    parameter_sources: Dict[str, str] = field(default_factory=dict)
    plugin_version: str = ""
    backend: str = "auto"
    sync_group_id: Optional[str] = None

    @classmethod
    def from_dict(cls, value: Any, path: str = "sensor") -> "SensorDefinition":
        data = expect_mapping(value, path)
        strict_keys(
            data,
            allowed={
                "sensor_id",
                "plugin",
                "prim_path",
                "enabled",
                "stage_parameters",
                "parameters",
                "parameter_sources",
                "plugin_version",
                "backend",
                "sync_group_id",
            },
            required={"sensor_id", "plugin", "prim_path"},
            path=path,
        )
        return cls(
            sensor_id=expect_string(data["sensor_id"], f"{path}.sensor_id"),
            plugin=expect_string(data["plugin"], f"{path}.plugin"),
            prim_path=expect_string(data["prim_path"], f"{path}.prim_path"),
            enabled=expect_bool(data.get("enabled", True), f"{path}.enabled"),
            stage_parameters=json_object(
                data.get("stage_parameters", {}), f"{path}.stage_parameters"
            ),
            parameters=json_object(data.get("parameters", {}), f"{path}.parameters"),
            parameter_sources=string_dict(
                data.get("parameter_sources", {}), f"{path}.parameter_sources"
            ),
            plugin_version=expect_string(
                data.get("plugin_version", ""),
                f"{path}.plugin_version",
                allow_empty=True,
            ),
            backend=expect_string(data.get("backend", "auto"), f"{path}.backend"),
            sync_group_id=_optional_string(
                data.get("sync_group_id"), f"{path}.sync_group_id"
            ),
        )


@dataclass(frozen=True)
class SensorBinding:
    """Normalized view of one sensor × variant modality selection."""

    sensor_id: str
    variant_id: str
    modality_ids: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return to_data(self)

    @classmethod
    def from_dict(cls, value: Any, path: str = "sensor_binding") -> "SensorBinding":
        data = expect_mapping(value, path)
        strict_keys(
            data,
            allowed={"sensor_id", "variant_id", "modality_ids"},
            required={"sensor_id", "variant_id", "modality_ids"},
            path=path,
        )
        return cls(
            sensor_id=expect_string(data["sensor_id"], f"{path}.sensor_id"),
            variant_id=expect_string(data["variant_id"], f"{path}.variant_id"),
            modality_ids=string_list(data["modality_ids"], f"{path}.modality_ids"),
        )


@dataclass
class VariantDefinition:
    variant_id: str
    strategy: str
    enabled: bool = True
    include_paths: List[str] = field(default_factory=list)
    exclude_paths: List[str] = field(default_factory=list)
    protected_paths: List[str] = field(default_factory=list)
    modalities_by_sensor: Dict[str, List[str]] = field(default_factory=dict)
    options: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Any, path: str = "variant") -> "VariantDefinition":
        data = expect_mapping(value, path)
        strict_keys(
            data,
            allowed={
                "variant_id",
                "strategy",
                "enabled",
                "include_paths",
                "exclude_paths",
                "protected_paths",
                "modalities_by_sensor",
                "options",
            },
            required={"variant_id", "strategy"},
            path=path,
        )
        modality_map_raw = expect_mapping(
            data.get("modalities_by_sensor", {}), f"{path}.modalities_by_sensor"
        )
        modality_map: Dict[str, List[str]] = {}
        for sensor_id, modalities in modality_map_raw.items():
            key = expect_string(sensor_id, f"{path}.modalities_by_sensor.<key>")
            modality_map[key] = string_list(
                modalities, f"{path}.modalities_by_sensor.{key}"
            )
        return cls(
            variant_id=expect_string(data["variant_id"], f"{path}.variant_id"),
            strategy=expect_string(data["strategy"], f"{path}.strategy"),
            enabled=expect_bool(data.get("enabled", True), f"{path}.enabled"),
            include_paths=string_list(data.get("include_paths", []), f"{path}.include_paths"),
            exclude_paths=string_list(data.get("exclude_paths", []), f"{path}.exclude_paths"),
            protected_paths=string_list(
                data.get("protected_paths", []), f"{path}.protected_paths"
            ),
            modalities_by_sensor=modality_map,
            options=json_object(data.get("options", {}), f"{path}.options"),
        )


@dataclass
class ModalityDefinition:
    modality_id: str
    plugin: str
    enabled: bool = True
    options: Dict[str, Any] = field(default_factory=dict)
    plugin_version: str = ""

    @classmethod
    def from_dict(cls, value: Any, path: str = "modality") -> "ModalityDefinition":
        data = expect_mapping(value, path)
        strict_keys(
            data,
            allowed={"modality_id", "plugin", "enabled", "options", "plugin_version"},
            required={"modality_id", "plugin"},
            path=path,
        )
        return cls(
            modality_id=expect_string(data["modality_id"], f"{path}.modality_id"),
            plugin=expect_string(data["plugin"], f"{path}.plugin"),
            enabled=expect_bool(data.get("enabled", True), f"{path}.enabled"),
            options=json_object(data.get("options", {}), f"{path}.options"),
            plugin_version=expect_string(
                data.get("plugin_version", ""),
                f"{path}.plugin_version",
                allow_empty=True,
            ),
        )


@dataclass
class RenderProfile:
    renderer: str = "RayTracedLighting"
    resolution_width: int = 640
    resolution_height: int = 480
    warmup_frames: int = 8
    rt_subframes: int = 1
    spp_per_frame: int = 1
    total_spp: int = 1
    max_bounces: int = 4
    denoiser: bool = True
    settings: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Any, path: str = "render") -> "RenderProfile":
        data = expect_mapping(value, path)
        allowed = {
            "renderer",
            "resolution_width",
            "resolution_height",
            "warmup_frames",
            "rt_subframes",
            "spp_per_frame",
            "total_spp",
            "max_bounces",
            "denoiser",
            "settings",
        }
        strict_keys(data, allowed=allowed, path=path)
        return cls(
            renderer=expect_string(
                data.get("renderer", "RayTracedLighting"), f"{path}.renderer"
            ),
            resolution_width=expect_int(
                data.get("resolution_width", 640), f"{path}.resolution_width"
            ),
            resolution_height=expect_int(
                data.get("resolution_height", 480), f"{path}.resolution_height"
            ),
            warmup_frames=expect_int(
                data.get("warmup_frames", 8), f"{path}.warmup_frames"
            ),
            rt_subframes=expect_int(
                data.get("rt_subframes", 1), f"{path}.rt_subframes"
            ),
            spp_per_frame=expect_int(
                data.get("spp_per_frame", 1), f"{path}.spp_per_frame"
            ),
            total_spp=expect_int(data.get("total_spp", 1), f"{path}.total_spp"),
            max_bounces=expect_int(
                data.get("max_bounces", 4), f"{path}.max_bounces"
            ),
            denoiser=expect_bool(data.get("denoiser", True), f"{path}.denoiser"),
            settings=json_object(data.get("settings", {}), f"{path}.settings"),
        )


@dataclass
class CaptureSchedule:
    physics_hz: int = 60
    capture_fps: int = 10
    start_frame: int = 0
    frame_count: int = 1
    capture_initial_frame: bool = True
    segment_frames: int = 100

    @classmethod
    def from_dict(cls, value: Any, path: str = "capture") -> "CaptureSchedule":
        data = expect_mapping(value, path)
        strict_keys(
            data,
            allowed={
                "physics_hz",
                "capture_fps",
                "start_frame",
                "frame_count",
                "capture_initial_frame",
                "segment_frames",
            },
            path=path,
        )
        return cls(
            physics_hz=expect_int(data.get("physics_hz", 60), f"{path}.physics_hz"),
            capture_fps=expect_int(data.get("capture_fps", 10), f"{path}.capture_fps"),
            start_frame=expect_int(data.get("start_frame", 0), f"{path}.start_frame"),
            frame_count=expect_int(data.get("frame_count", 1), f"{path}.frame_count"),
            capture_initial_frame=expect_bool(
                data.get("capture_initial_frame", True), f"{path}.capture_initial_frame"
            ),
            segment_frames=expect_int(
                data.get("segment_frames", 100), f"{path}.segment_frames"
            ),
        )


@dataclass
class MotionSpec:
    plugin: str = "none"
    source_path: Optional[str] = None
    supports_absolute_seek: bool = False
    options: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Any, path: str = "motion") -> "MotionSpec":
        data = expect_mapping(value, path)
        strict_keys(
            data,
            allowed={"plugin", "source_path", "supports_absolute_seek", "options"},
            path=path,
        )
        source = data.get("source_path")
        return cls(
            plugin=expect_string(data.get("plugin", "none"), f"{path}.plugin"),
            source_path=(
                None if source is None else expect_string(source, f"{path}.source_path")
            ),
            supports_absolute_seek=expect_bool(
                data.get("supports_absolute_seek", False),
                f"{path}.supports_absolute_seek",
            ),
            options=json_object(data.get("options", {}), f"{path}.options"),
        )


@dataclass
class SemanticProfile:
    mapping_path: Optional[str] = None
    label_attribute: str = "class"
    background_id: int = 0
    options: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Any, path: str = "semantics") -> "SemanticProfile":
        data = expect_mapping(value, path)
        strict_keys(
            data,
            allowed={"mapping_path", "label_attribute", "background_id", "options"},
            path=path,
        )
        mapping_path = data.get("mapping_path")
        return cls(
            mapping_path=(
                None
                if mapping_path is None
                else expect_string(mapping_path, f"{path}.mapping_path")
            ),
            label_attribute=expect_string(
                data.get("label_attribute", "class"), f"{path}.label_attribute"
            ),
            background_id=expect_int(
                data.get("background_id", 0), f"{path}.background_id"
            ),
            options=json_object(data.get("options", {}), f"{path}.options"),
        )


@dataclass
class OutputPolicy:
    root_dir: str = "output"
    overwrite: bool = False
    atomic_frames: bool = True
    retain_staging_on_failure: bool = True

    @classmethod
    def from_dict(cls, value: Any, path: str = "output") -> "OutputPolicy":
        data = expect_mapping(value, path)
        strict_keys(
            data,
            allowed={
                "root_dir",
                "overwrite",
                "atomic_frames",
                "retain_staging_on_failure",
            },
            path=path,
        )
        return cls(
            root_dir=expect_string(data.get("root_dir", "output"), f"{path}.root_dir"),
            overwrite=expect_bool(data.get("overwrite", False), f"{path}.overwrite"),
            atomic_frames=expect_bool(
                data.get("atomic_frames", True), f"{path}.atomic_frames"
            ),
            retain_staging_on_failure=expect_bool(
                data.get("retain_staging_on_failure", True),
                f"{path}.retain_staging_on_failure",
            ),
        )


@dataclass
class ExecutionPolicy:
    segmentation_strategy: str = "auto"
    heartbeat_timeout_seconds: float = 120.0
    no_progress_timeout_seconds: float = 600.0
    segment_start_timeout_seconds: float = 300.0
    graceful_stop_timeout_seconds: float = 30.0
    telemetry_interval_seconds: float = 5.0

    @classmethod
    def from_dict(cls, value: Any, path: str = "execution") -> "ExecutionPolicy":
        data = expect_mapping(value, path)
        strict_keys(
            data,
            allowed={
                "segmentation_strategy",
                "heartbeat_timeout_seconds",
                "no_progress_timeout_seconds",
                "segment_start_timeout_seconds",
                "graceful_stop_timeout_seconds",
                "telemetry_interval_seconds",
            },
            path=path,
        )
        return cls(
            segmentation_strategy=expect_string(
                data.get("segmentation_strategy", "auto"),
                f"{path}.segmentation_strategy",
            ),
            heartbeat_timeout_seconds=expect_number(
                data.get("heartbeat_timeout_seconds", 120.0),
                f"{path}.heartbeat_timeout_seconds",
            ),
            no_progress_timeout_seconds=expect_number(
                data.get("no_progress_timeout_seconds", 600.0),
                f"{path}.no_progress_timeout_seconds",
            ),
            segment_start_timeout_seconds=expect_number(
                data.get("segment_start_timeout_seconds", 300.0),
                f"{path}.segment_start_timeout_seconds",
            ),
            graceful_stop_timeout_seconds=expect_number(
                data.get("graceful_stop_timeout_seconds", 30.0),
                f"{path}.graceful_stop_timeout_seconds",
            ),
            telemetry_interval_seconds=expect_number(
                data.get("telemetry_interval_seconds", 5.0),
                f"{path}.telemetry_interval_seconds",
            ),
        )


@dataclass
class ProjectDefinition:
    project_id: str
    name: str
    stage: StageReference
    sensors: List[SensorDefinition]
    variants: List[VariantDefinition]
    modalities: List[ModalityDefinition]
    render: RenderProfile = field(default_factory=RenderProfile)
    capture: CaptureSchedule = field(default_factory=CaptureSchedule)
    motion: MotionSpec = field(default_factory=MotionSpec)
    semantics: SemanticProfile = field(default_factory=SemanticProfile)
    output: OutputPolicy = field(default_factory=OutputPolicy)
    execution: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    rigs: List[RigDefinition] = field(default_factory=list)
    description: str = ""
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return to_data(self)

    @classmethod
    def from_dict(cls, value: Any, path: str = "project") -> "ProjectDefinition":
        data = expect_mapping(value, path)
        allowed = {
            "schema_version",
            "project_id",
            "name",
            "description",
            "stage",
            "sensors",
            "variants",
            "modalities",
            "render",
            "capture",
            "motion",
            "semantics",
            "output",
            "execution",
            "rigs",
        }
        strict_keys(
            data,
            allowed=allowed,
            required={"project_id", "name", "stage", "sensors", "variants", "modalities"},
            path=path,
        )
        version = _schema_version(data, path)
        sensors_raw = expect_list(data["sensors"], f"{path}.sensors")
        variants_raw = expect_list(data["variants"], f"{path}.variants")
        modalities_raw = expect_list(data["modalities"], f"{path}.modalities")
        rigs_raw = expect_list(data.get("rigs", []), f"{path}.rigs")
        return cls(
            schema_version=version,
            project_id=expect_string(data["project_id"], f"{path}.project_id"),
            name=expect_string(data["name"], f"{path}.name"),
            description=expect_string(
                data.get("description", ""), f"{path}.description", allow_empty=True
            ),
            stage=StageReference.from_dict(data["stage"], f"{path}.stage"),
            sensors=[
                SensorDefinition.from_dict(item, f"{path}.sensors[{index}]")
                for index, item in enumerate(sensors_raw)
            ],
            variants=[
                VariantDefinition.from_dict(item, f"{path}.variants[{index}]")
                for index, item in enumerate(variants_raw)
            ],
            modalities=[
                ModalityDefinition.from_dict(item, f"{path}.modalities[{index}]")
                for index, item in enumerate(modalities_raw)
            ],
            render=RenderProfile.from_dict(data.get("render", {}), f"{path}.render"),
            capture=CaptureSchedule.from_dict(
                data.get("capture", {}), f"{path}.capture"
            ),
            motion=MotionSpec.from_dict(data.get("motion", {}), f"{path}.motion"),
            semantics=SemanticProfile.from_dict(
                data.get("semantics", {}), f"{path}.semantics"
            ),
            output=OutputPolicy.from_dict(data.get("output", {}), f"{path}.output"),
            execution=ExecutionPolicy.from_dict(
                data.get("execution", {}), f"{path}.execution"
            ),
            rigs=[
                RigDefinition.from_dict(item, f"{path}.rigs[{index}]")
                for index, item in enumerate(rigs_raw)
            ],
        )


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    path: str
    severity: str = "error"
    hint: Optional[str] = None

    def __str__(self) -> str:
        location = f" at {self.path}" if self.path else ""
        return f"[{self.code}]{location}: {self.message}"


@dataclass(frozen=True)
class JobSpec:
    schema_version: int
    job_id: str
    compiled_at_utc: str
    source_project_path: str
    project: ProjectDefinition
    content_digest: str

    def to_dict(self) -> Dict[str, Any]:
        return to_data(self)

    @classmethod
    def from_dict(cls, value: Any, path: str = "job_spec") -> "JobSpec":
        data = expect_mapping(value, path)
        strict_keys(
            data,
            allowed={
                "schema_version",
                "job_id",
                "compiled_at_utc",
                "source_project_path",
                "project",
                "content_digest",
            },
            required={
                "schema_version",
                "job_id",
                "compiled_at_utc",
                "source_project_path",
                "project",
                "content_digest",
            },
            path=path,
        )
        version = _schema_version(data, path)
        return cls(
            schema_version=version,
            job_id=expect_string(data["job_id"], f"{path}.job_id"),
            compiled_at_utc=expect_string(
                data["compiled_at_utc"], f"{path}.compiled_at_utc"
            ),
            source_project_path=expect_string(
                data["source_project_path"],
                f"{path}.source_project_path",
                allow_empty=True,
            ),
            project=ProjectDefinition.from_dict(data["project"], f"{path}.project"),
            content_digest=expect_string(
                data["content_digest"], f"{path}.content_digest"
            ),
        )


@dataclass
class JobStatus:
    job_id: str
    state: str = "queued"
    created_at_utc: str = ""
    updated_at_utc: str = ""
    pid: Optional[int] = None
    process_token: Optional[str] = None
    started_at_utc: Optional[str] = None
    completed_at_utc: Optional[str] = None
    exit_code: Optional[int] = None
    last_heartbeat_utc: Optional[str] = None
    frame_current: int = 0
    frame_total: int = 0
    segment_current: int = 0
    segment_total: int = 0
    current_segment_id: Optional[str] = None
    last_commit_utc: Optional[str] = None
    estimated_remaining_seconds: Optional[float] = None
    gpu_memory_used_mb: Optional[int] = None
    failure_report_path: Optional[str] = None
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return to_data(self)

    @classmethod
    def from_dict(cls, value: Any, path: str = "job_status") -> "JobStatus":
        data = expect_mapping(value, path)
        allowed = {
            "job_id",
            "state",
            "created_at_utc",
            "updated_at_utc",
            "pid",
            "process_token",
            "started_at_utc",
            "completed_at_utc",
            "exit_code",
            "last_heartbeat_utc",
            "frame_current",
            "frame_total",
            "segment_current",
            "segment_total",
            "current_segment_id",
            "last_commit_utc",
            "estimated_remaining_seconds",
            "gpu_memory_used_mb",
            "failure_report_path",
            "message",
        }
        strict_keys(data, allowed=allowed, required={"job_id"}, path=path)
        pid_value = data.get("pid")
        exit_value = data.get("exit_code")
        remaining_value = data.get("estimated_remaining_seconds")
        memory_value = data.get("gpu_memory_used_mb")
        return cls(
            job_id=expect_string(data["job_id"], f"{path}.job_id"),
            state=expect_string(data.get("state", "queued"), f"{path}.state"),
            created_at_utc=expect_string(
                data.get("created_at_utc", ""),
                f"{path}.created_at_utc",
                allow_empty=True,
            ),
            updated_at_utc=expect_string(
                data.get("updated_at_utc", ""),
                f"{path}.updated_at_utc",
                allow_empty=True,
            ),
            pid=None if pid_value is None else expect_int(pid_value, f"{path}.pid"),
            process_token=_optional_string(
                data.get("process_token"), f"{path}.process_token"
            ),
            started_at_utc=_optional_string(data.get("started_at_utc"), f"{path}.started_at_utc"),
            completed_at_utc=_optional_string(
                data.get("completed_at_utc"), f"{path}.completed_at_utc"
            ),
            exit_code=(
                None if exit_value is None else expect_int(exit_value, f"{path}.exit_code")
            ),
            last_heartbeat_utc=_optional_string(
                data.get("last_heartbeat_utc"), f"{path}.last_heartbeat_utc"
            ),
            frame_current=expect_int(
                data.get("frame_current", 0), f"{path}.frame_current"
            ),
            frame_total=expect_int(data.get("frame_total", 0), f"{path}.frame_total"),
            segment_current=expect_int(
                data.get("segment_current", 0), f"{path}.segment_current"
            ),
            segment_total=expect_int(
                data.get("segment_total", 0), f"{path}.segment_total"
            ),
            current_segment_id=_optional_string(
                data.get("current_segment_id"), f"{path}.current_segment_id"
            ),
            last_commit_utc=_optional_string(
                data.get("last_commit_utc"), f"{path}.last_commit_utc"
            ),
            estimated_remaining_seconds=(
                None
                if remaining_value is None
                else expect_number(remaining_value, f"{path}.estimated_remaining_seconds")
            ),
            gpu_memory_used_mb=(
                None
                if memory_value is None
                else expect_int(memory_value, f"{path}.gpu_memory_used_mb")
            ),
            failure_report_path=_optional_string(
                data.get("failure_report_path"), f"{path}.failure_report_path"
            ),
            message=expect_string(
                data.get("message", ""), f"{path}.message", allow_empty=True
            ),
        )


@dataclass(frozen=True)
class SegmentSpec:
    schema_version: int
    job_id: str
    job_content_digest: str
    segment_id: str
    segment_index: int
    start_frame: int
    frame_count: int
    end_frame_exclusive: int
    expected_capture_groups: int
    motion_positioning: str
    variant_ids: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return to_data(self)

    @classmethod
    def from_dict(cls, value: Any, path: str = "segment_spec") -> "SegmentSpec":
        data = expect_mapping(value, path)
        strict_keys(
            data,
            allowed={
                "schema_version",
                "job_id",
                "job_content_digest",
                "segment_id",
                "segment_index",
                "start_frame",
                "frame_count",
                "end_frame_exclusive",
                "expected_capture_groups",
                "motion_positioning",
                "variant_ids",
            },
            required={
                "schema_version",
                "job_id",
                "job_content_digest",
                "segment_id",
                "segment_index",
                "start_frame",
                "frame_count",
                "end_frame_exclusive",
                "expected_capture_groups",
                "motion_positioning",
                "variant_ids",
            },
            path=path,
        )
        return cls(
            schema_version=_schema_version(data, path),
            job_id=expect_string(data["job_id"], f"{path}.job_id"),
            job_content_digest=expect_string(
                data["job_content_digest"], f"{path}.job_content_digest"
            ),
            segment_id=expect_string(data["segment_id"], f"{path}.segment_id"),
            segment_index=expect_int(data["segment_index"], f"{path}.segment_index"),
            start_frame=expect_int(data["start_frame"], f"{path}.start_frame"),
            frame_count=expect_int(data["frame_count"], f"{path}.frame_count"),
            end_frame_exclusive=expect_int(
                data["end_frame_exclusive"], f"{path}.end_frame_exclusive"
            ),
            expected_capture_groups=expect_int(
                data["expected_capture_groups"], f"{path}.expected_capture_groups"
            ),
            motion_positioning=expect_string(
                data["motion_positioning"], f"{path}.motion_positioning"
            ),
            variant_ids=string_list(data["variant_ids"], f"{path}.variant_ids"),
        )


@dataclass
class SegmentStatus:
    job_id: str
    segment_id: str
    state: str = "planned"
    created_at_utc: str = ""
    updated_at_utc: str = ""
    pid: Optional[int] = None
    process_token: Optional[str] = None
    started_at_utc: Optional[str] = None
    completed_at_utc: Optional[str] = None
    exit_code: Optional[int] = None
    last_heartbeat_utc: Optional[str] = None
    last_commit_utc: Optional[str] = None
    capture_groups_current: int = 0
    capture_groups_total: int = 0
    failure_code: Optional[str] = None
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return to_data(self)

    @classmethod
    def from_dict(cls, value: Any, path: str = "segment_status") -> "SegmentStatus":
        data = expect_mapping(value, path)
        allowed = {
            "job_id",
            "segment_id",
            "state",
            "created_at_utc",
            "updated_at_utc",
            "pid",
            "process_token",
            "started_at_utc",
            "completed_at_utc",
            "exit_code",
            "last_heartbeat_utc",
            "last_commit_utc",
            "capture_groups_current",
            "capture_groups_total",
            "failure_code",
            "message",
        }
        strict_keys(
            data,
            allowed=allowed,
            required={"job_id", "segment_id"},
            path=path,
        )
        pid_value = data.get("pid")
        exit_value = data.get("exit_code")
        return cls(
            job_id=expect_string(data["job_id"], f"{path}.job_id"),
            segment_id=expect_string(data["segment_id"], f"{path}.segment_id"),
            state=expect_string(data.get("state", "planned"), f"{path}.state"),
            created_at_utc=expect_string(
                data.get("created_at_utc", ""), f"{path}.created_at_utc", allow_empty=True
            ),
            updated_at_utc=expect_string(
                data.get("updated_at_utc", ""), f"{path}.updated_at_utc", allow_empty=True
            ),
            pid=None if pid_value is None else expect_int(pid_value, f"{path}.pid"),
            process_token=_optional_string(
                data.get("process_token"), f"{path}.process_token"
            ),
            started_at_utc=_optional_string(
                data.get("started_at_utc"), f"{path}.started_at_utc"
            ),
            completed_at_utc=_optional_string(
                data.get("completed_at_utc"), f"{path}.completed_at_utc"
            ),
            exit_code=None
            if exit_value is None
            else expect_int(exit_value, f"{path}.exit_code"),
            last_heartbeat_utc=_optional_string(
                data.get("last_heartbeat_utc"), f"{path}.last_heartbeat_utc"
            ),
            last_commit_utc=_optional_string(
                data.get("last_commit_utc"), f"{path}.last_commit_utc"
            ),
            capture_groups_current=expect_int(
                data.get("capture_groups_current", 0),
                f"{path}.capture_groups_current",
            ),
            capture_groups_total=expect_int(
                data.get("capture_groups_total", 0),
                f"{path}.capture_groups_total",
            ),
            failure_code=_optional_string(
                data.get("failure_code"), f"{path}.failure_code"
            ),
            message=expect_string(
                data.get("message", ""), f"{path}.message", allow_empty=True
            ),
        )


@dataclass(frozen=True)
class FrameLedgerEntry:
    frame_index: int
    sensor_id: str
    variant_id: str
    simulation_time: float
    requested_modalities: List[str]
    files: Dict[str, str]
    committed_at_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return to_data(self)

    @classmethod
    def from_dict(cls, value: Any, path: str = "ledger_entry") -> "FrameLedgerEntry":
        data = expect_mapping(value, path)
        strict_keys(
            data,
            allowed={
                "frame_index",
                "sensor_id",
                "variant_id",
                "simulation_time",
                "requested_modalities",
                "files",
                "committed_at_utc",
            },
            required={
                "frame_index",
                "sensor_id",
                "variant_id",
                "simulation_time",
                "requested_modalities",
                "files",
                "committed_at_utc",
            },
            path=path,
        )
        return cls(
            frame_index=expect_int(data["frame_index"], f"{path}.frame_index"),
            sensor_id=expect_string(data["sensor_id"], f"{path}.sensor_id"),
            variant_id=expect_string(data["variant_id"], f"{path}.variant_id"),
            simulation_time=expect_number(
                data["simulation_time"], f"{path}.simulation_time"
            ),
            requested_modalities=string_list(
                data["requested_modalities"], f"{path}.requested_modalities"
            ),
            files=string_dict(data["files"], f"{path}.files"),
            committed_at_utc=expect_string(
                data["committed_at_utc"], f"{path}.committed_at_utc"
            ),
        )


def _optional_string(value: Any, path: str) -> Optional[str]:
    if value is None:
        return None
    return expect_string(value, path, allow_empty=True)
