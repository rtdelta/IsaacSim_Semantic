"""Runtime-checkable contracts between pure core and environment adapters."""

from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Protocol, Sequence, runtime_checkable

from .models import (
    FrameLedgerEntry,
    JobSpec,
    JobStatus,
    ProjectDefinition,
    SensorDefinition,
    ValidationIssue,
    VariantDefinition,
)
from .sensor_models import (
    CaptureContext,
    PluginManifest,
    SensorCapabilities,
    SensorSample,
)


@runtime_checkable
class ProjectRepositoryProtocol(Protocol):
    def save(self, project_dir: Path, project: ProjectDefinition) -> None:
        ...

    def load(self, project_dir: Path) -> ProjectDefinition:
        ...


@runtime_checkable
class StageIndexProtocol(Protocol):
    def get(self, prim_path: str) -> Optional[Any]:
        ...

    def iter_prims(self) -> Iterable[Any]:
        ...


@runtime_checkable
class SensorPluginProtocol(Protocol):
    plugin_id: str

    def manifest(self) -> PluginManifest:
        ...

    def capabilities(self) -> SensorCapabilities:
        ...

    def parameter_schema(self) -> Mapping[str, Any]:
        ...

    def matches_prim(self, prim: Any) -> bool:
        ...

    def extract_stage_parameters(self, prim: Any) -> Dict[str, Any]:
        ...

    def supported_modalities(self) -> Sequence[str]:
        ...

    def validate(
        self, sensor: SensorDefinition, stage_index: Optional[StageIndexProtocol]
    ) -> Sequence[ValidationIssue]:
        ...

    def compile_runtime_payload(
        self, sensor: SensorDefinition, stage_index: Optional[StageIndexProtocol]
    ) -> Mapping[str, Any]:
        ...

    def create_runtime_driver(
        self,
        sensor: SensorDefinition,
        *,
        resolution: Sequence[int],
        modalities: Sequence[str],
    ) -> Any:
        ...

    def author_runtime_overrides(
        self, stage: Any, sensor: SensorDefinition
    ) -> Mapping[str, Any]:
        ...


@runtime_checkable
class VariantStrategyProtocol(Protocol):
    strategy_id: str

    def validate(
        self, variant: VariantDefinition, stage_index: Optional[StageIndexProtocol]
    ) -> Sequence[ValidationIssue]:
        ...

    def visibility_plan(
        self,
        variant: VariantDefinition,
        stage_index: StageIndexProtocol,
        sensor_paths: Sequence[str],
    ) -> Any:
        ...


@runtime_checkable
class ModalityPluginProtocol(Protocol):
    plugin_id: str

    def manifest(self) -> PluginManifest:
        ...

    def validate_options(self, options: Mapping[str, Any]) -> Sequence[ValidationIssue]:
        ...

    def encode_runtime(
        self, payload: Mapping[str, Any], context: Mapping[str, Any]
    ) -> Any:
        ...


@runtime_checkable
class SensorRuntimeDriverProtocol(Protocol):
    sensor_id: str
    capture_trigger_key: str

    def preflight(self, stage: Any) -> None:
        ...

    def initialize(self, stage: Any) -> None:
        ...

    def trigger_capture(self, rt_subframes: int) -> None:
        ...

    def read(self, requested_modalities: Sequence[str]) -> Mapping[str, Any]:
        ...

    def read_sample(
        self,
        requested_modalities: Sequence[str],
        context: CaptureContext,
    ) -> SensorSample:
        ...

    def close(self) -> None:
        ...


@runtime_checkable
class JobSupervisorProtocol(Protocol):
    def submit(self, job_spec: JobSpec) -> JobStatus:
        ...

    def start(self, job_id: str) -> JobStatus:
        ...

    def status(self, job_id: str) -> JobStatus:
        ...

    def stop(self, job_id: str) -> JobStatus:
        ...


@runtime_checkable
class LedgerProtocol(Protocol):
    def append(self, entry: FrameLedgerEntry) -> None:
        ...

    def is_committed(
        self, frame_index: int, sensor_id: str, variant_id: str
    ) -> bool:
        ...
