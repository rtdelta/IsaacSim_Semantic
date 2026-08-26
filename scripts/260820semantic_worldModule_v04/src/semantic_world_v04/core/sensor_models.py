"""Pure-Python contracts for heterogeneous sensors and capture payloads.

This module deliberately has no USD, Kit, Isaac Sim, NumPy, or GPU imports so
the same contracts can be used by Studio, the compiler, tests, and headless
workers.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

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
    string_list,
    to_data,
)

PLUGIN_CONTRACT_VERSION = 2

PAYLOAD_KINDS = {"raster", "dense_array", "point_cloud", "records"}
TIME_MODELS = {"instantaneous", "exposure_window", "scan_window"}
SYNC_MODES = {"single", "shared_trigger", "rig_batch"}


@dataclass(frozen=True)
class PluginManifest:
    plugin_id: str
    plugin_kind: str
    plugin_version: str
    display_name: str
    contract_version: int = PLUGIN_CONTRACT_VERSION
    definition_class: str = ""
    runtime_requirements: Tuple[str, ...] = ()
    supported_modalities: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return to_data(self)

    @classmethod
    def from_dict(cls, value: Any, path: str = "plugin_manifest") -> "PluginManifest":
        data = expect_mapping(value, path)
        strict_keys(
            data,
            allowed={
                "plugin_id",
                "plugin_kind",
                "plugin_version",
                "display_name",
                "contract_version",
                "definition_class",
                "runtime_requirements",
                "supported_modalities",
            },
            required={"plugin_id", "plugin_kind", "plugin_version", "display_name"},
            path=path,
        )
        kind = expect_string(data["plugin_kind"], f"{path}.plugin_kind")
        if kind not in {"sensor", "modality", "variant"}:
            raise SchemaError("must be sensor, modality, or variant", f"{path}.plugin_kind")
        requirements = string_list(
            data.get("runtime_requirements", []),
            f"{path}.runtime_requirements",
        )
        modalities = string_list(
            data.get("supported_modalities", []),
            f"{path}.supported_modalities",
        )
        return cls(
            plugin_id=expect_string(data["plugin_id"], f"{path}.plugin_id"),
            plugin_kind=kind,
            plugin_version=expect_string(
                data["plugin_version"], f"{path}.plugin_version"
            ),
            display_name=expect_string(data["display_name"], f"{path}.display_name"),
            contract_version=expect_int(
                data.get("contract_version", PLUGIN_CONTRACT_VERSION),
                f"{path}.contract_version",
            ),
            definition_class=expect_string(
                data.get("definition_class", ""),
                f"{path}.definition_class",
                allow_empty=True,
            ),
            runtime_requirements=tuple(requirements),
            supported_modalities=tuple(modalities),
        )


@dataclass(frozen=True)
class SensorCapabilities:
    payload_kinds: Tuple[str, ...]
    time_model: str = "instantaneous"
    trigger_domain: str = "custom"
    synchronization_mode: str = "single"
    renderer_compatibility: Tuple[str, ...] = (
        "RayTracedLighting",
        "PathTracing",
    )
    requires_continuous_history: bool = False
    supports_stage_overrides: bool = True
    calibration_model: str = "none"
    backend_requirements: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        unknown_payloads = sorted(set(self.payload_kinds) - PAYLOAD_KINDS)
        if unknown_payloads:
            raise ValueError(f"unknown payload kind(s): {', '.join(unknown_payloads)}")
        if self.time_model not in TIME_MODELS:
            raise ValueError(f"unknown sensor time model: {self.time_model}")
        if self.synchronization_mode not in SYNC_MODES:
            raise ValueError(
                f"unknown synchronization mode: {self.synchronization_mode}"
            )
        if not self.trigger_domain:
            raise ValueError("trigger_domain must not be empty")

    def to_dict(self) -> Dict[str, Any]:
        return to_data(self)


@dataclass
class RigDefinition:
    rig_id: str
    sensor_ids: List[str]
    sync_policy: str = "same_simulation_step"
    failure_policy: str = "all_or_retry"
    reference_frame_prim_path: Optional[str] = None
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return to_data(self)

    @classmethod
    def from_dict(cls, value: Any, path: str = "rig") -> "RigDefinition":
        data = expect_mapping(value, path)
        strict_keys(
            data,
            allowed={
                "rig_id",
                "sensor_ids",
                "sync_policy",
                "failure_policy",
                "reference_frame_prim_path",
                "enabled",
            },
            required={"rig_id", "sensor_ids"},
            path=path,
        )
        reference = data.get("reference_frame_prim_path")
        return cls(
            rig_id=expect_string(data["rig_id"], f"{path}.rig_id"),
            sensor_ids=string_list(data["sensor_ids"], f"{path}.sensor_ids"),
            sync_policy=expect_string(
                data.get("sync_policy", "same_simulation_step"),
                f"{path}.sync_policy",
            ),
            failure_policy=expect_string(
                data.get("failure_policy", "all_or_retry"),
                f"{path}.failure_policy",
            ),
            reference_frame_prim_path=(
                None
                if reference is None
                else expect_string(reference, f"{path}.reference_frame_prim_path")
            ),
            enabled=expect_bool(data.get("enabled", True), f"{path}.enabled"),
        )


@dataclass(frozen=True)
class EffectiveSensorConfig:
    sensor_id: str
    plugin_id: str
    plugin_version: str
    prim_path: str
    stage_parameters: Mapping[str, Any]
    default_parameters: Mapping[str, Any]
    override_parameters: Mapping[str, Any]
    effective_parameters: Mapping[str, Any]
    parameter_sources: Mapping[str, str]
    sync_group_id: str
    backend_id: str = "auto"

    def to_dict(self) -> Dict[str, Any]:
        return to_data(self)


@dataclass(frozen=True)
class CalibrationSnapshot:
    sensor_id: str
    model: str
    prim_path: str
    parameters: Mapping[str, Any]
    sensor_to_world: Sequence[Sequence[float]] = ()
    coordinate_frame: str = "world"
    meters_per_unit: float = 1.0
    backend_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return to_data(self)


@dataclass(frozen=True)
class CaptureContext:
    job_id: str
    segment_id: str
    frame_index: int
    simulation_step: int
    simulation_time_seconds: float
    capture_timestamp: str
    variant_id: str
    sync_group_id: str
    renderer: str
    meters_per_unit: float = 1.0
    world_coordinate_convention: str = "USD right-handed, Y-up"

    def to_dict(self) -> Dict[str, Any]:
        return to_data(self)


@dataclass(frozen=True)
class TypedPayload:
    """One in-memory sensor payload plus its semantic description."""

    kind: str
    data: Any
    dtype: str = ""
    shape: Tuple[int, ...] = ()
    unit: str = ""
    coordinate_frame: str = ""
    fields: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in PAYLOAD_KINDS:
            raise ValueError(f"unknown payload kind: {self.kind}")
        if any(int(value) < 0 for value in self.shape):
            raise ValueError("payload shape dimensions must not be negative")

    def descriptor(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "unit": self.unit,
            "coordinate_frame": self.coordinate_frame,
            "fields": list(self.fields),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SensorSample:
    sensor_id: str
    timestamp: str
    modality_payloads: Mapping[str, TypedPayload]
    calibration_snapshot: CalibrationSnapshot
    sequence_metadata: Mapping[str, Any] = field(default_factory=dict)
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaptureBatchKey:
    frame_index: int
    variant_id: str
    sync_group_id: str

    def token(self) -> str:
        return (
            f"frame_{self.frame_index:06d}__{self.variant_id}__"
            f"{self.sync_group_id}"
        )


@dataclass(frozen=True)
class BatchLedgerEntry:
    frame_index: int
    variant_id: str
    sync_group_id: str
    simulation_time: float
    sensor_ids: List[str]
    frame_keys: List[str]
    committed_at_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return to_data(self)

    @classmethod
    def from_dict(
        cls, value: Any, path: str = "batch_ledger_entry"
    ) -> "BatchLedgerEntry":
        data = expect_mapping(value, path)
        strict_keys(
            data,
            allowed={
                "frame_index",
                "variant_id",
                "sync_group_id",
                "simulation_time",
                "sensor_ids",
                "frame_keys",
                "committed_at_utc",
            },
            required={
                "frame_index",
                "variant_id",
                "sync_group_id",
                "simulation_time",
                "sensor_ids",
                "frame_keys",
                "committed_at_utc",
            },
            path=path,
        )
        return cls(
            frame_index=expect_int(data["frame_index"], f"{path}.frame_index"),
            variant_id=expect_string(data["variant_id"], f"{path}.variant_id"),
            sync_group_id=expect_string(
                data["sync_group_id"], f"{path}.sync_group_id"
            ),
            simulation_time=expect_number(
                data["simulation_time"], f"{path}.simulation_time"
            ),
            sensor_ids=string_list(data["sensor_ids"], f"{path}.sensor_ids"),
            frame_keys=string_list(data["frame_keys"], f"{path}.frame_keys"),
            committed_at_utc=expect_string(
                data["committed_at_utc"], f"{path}.committed_at_utc"
            ),
        )


def infer_shape(value: Any) -> Tuple[int, ...]:
    """Infer a NumPy-like shape without importing NumPy."""

    shape = getattr(value, "shape", None)
    if shape is not None:
        try:
            return tuple(int(item) for item in shape)
        except (TypeError, ValueError):
            return ()
    if isinstance(value, (list, tuple)):
        if not value:
            return (0,)
        return (len(value),) + infer_shape(value[0])
    return ()


def parameter_schema(fields: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """Build the small JSON-schema subset understood by the Studio form."""

    properties: Dict[str, Any] = {}
    required: List[str] = []
    for name, definition in fields.items():
        item = json_object(definition, f"parameter_schema.{name}")
        if bool(item.pop("required", False)):
            required.append(name)
        properties[name] = item
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": sorted(required),
    }


def parameter_schema_issues(
    values: Mapping[str, Any],
    schema: Mapping[str, Any],
    *,
    path: str = "parameters",
) -> List[str]:
    """Validate the JSON-schema subset emitted by :func:`parameter_schema`.

    This intentionally covers only the stable, UI-facing subset used by v04.3:
    object properties, required fields, scalar/array types, enums, bounds, and
    fixed array lengths.  It keeps Studio and the compiler dependency-free and
    produces deterministic messages instead of silently accepting misspelled
    override names.
    """

    issues: List[str] = []
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        return [f"{path}: schema properties must be an object"]
    if schema.get("additionalProperties") is False:
        for name in sorted(set(values) - set(properties)):
            issues.append(f"{path}.{name}: unknown parameter")
    required = schema.get("required", [])
    if isinstance(required, (list, tuple)):
        for name in required:
            if name not in values:
                issues.append(f"{path}.{name}: required parameter is missing")

    for name, value in values.items():
        definition = properties.get(name)
        if not isinstance(definition, Mapping):
            continue
        item_path = f"{path}.{name}"
        expected = definition.get("type")
        valid_type = True
        if expected == "string":
            valid_type = isinstance(value, str)
        elif expected == "number":
            valid_type = isinstance(value, (int, float)) and not isinstance(value, bool)
        elif expected == "integer":
            valid_type = isinstance(value, int) and not isinstance(value, bool)
        elif expected == "boolean":
            valid_type = isinstance(value, bool)
        elif expected == "array":
            valid_type = isinstance(value, (list, tuple))
        elif expected == "object":
            valid_type = isinstance(value, Mapping)
        if not valid_type:
            issues.append(f"{item_path}: expected {expected}")
            continue
        enum = definition.get("enum")
        if isinstance(enum, (list, tuple)) and value not in enum:
            issues.append(f"{item_path}: must be one of {list(enum)!r}")
        if expected in {"number", "integer"}:
            minimum = definition.get("minimum")
            maximum = definition.get("maximum")
            if isinstance(minimum, (int, float)) and value < minimum:
                issues.append(f"{item_path}: must be >= {minimum}")
            if isinstance(maximum, (int, float)) and value > maximum:
                issues.append(f"{item_path}: must be <= {maximum}")
        if expected == "array":
            minimum_items = definition.get("minItems")
            maximum_items = definition.get("maxItems")
            if isinstance(minimum_items, int) and len(value) < minimum_items:
                issues.append(f"{item_path}: requires at least {minimum_items} items")
            if isinstance(maximum_items, int) and len(value) > maximum_items:
                issues.append(f"{item_path}: allows at most {maximum_items} items")
            item_schema = definition.get("items")
            if isinstance(item_schema, Mapping):
                for index, child in enumerate(value):
                    child_issues = parameter_schema_issues(
                        {"value": child},
                        {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {"value": item_schema},
                        },
                        path=f"{item_path}[{index}]",
                    )
                    issues.extend(
                        issue.replace(
                            f"{item_path}[{index}].value", f"{item_path}[{index}]"
                        )
                        for issue in child_issues
                    )
    return issues
