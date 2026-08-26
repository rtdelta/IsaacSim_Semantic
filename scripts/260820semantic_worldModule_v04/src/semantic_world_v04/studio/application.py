"""Application services used by Kit widgets and command-line probes."""

from copy import deepcopy
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from semantic_world_v04.compiler import JobCompiler, ProjectValidator
from semantic_world_v04.core.models import (
    CaptureSchedule,
    ExecutionPolicy,
    JobSpec,
    JobStatus,
    ModalityDefinition,
    MotionSpec,
    OutputPolicy,
    ProjectDefinition,
    RenderProfile,
    SemanticProfile,
    SCHEMA_VERSION,
    SensorDefinition,
    StageReference,
    VariantDefinition,
    ValidationIssue,
)
from semantic_world_v04.core.sensor_models import RigDefinition, parameter_schema_issues
from semantic_world_v04.output.io import atomic_write_json
from semantic_world_v04.output.io import read_json
from semantic_world_v04.output.status_store import StatusStore
from semantic_world_v04.output.segment_store import SegmentStatusStore
from semantic_world_v04.plugins import PluginRegistry, build_default_registry
from semantic_world_v04.project import ProjectRepository
from semantic_world_v04.project.paths import ProjectPathResolver
from semantic_world_v04.stage import StageIndex
from semantic_world_v04.supervisor import SameHostSupervisor

from .preflight import estimate_output


class StudioController:
    """Coordinate project editing without importing omni.ui or Isaac Sim."""

    def __init__(
        self,
        *,
        repository: Optional[ProjectRepository] = None,
        registry: Optional[PluginRegistry] = None,
        supervisor: Optional[SameHostSupervisor] = None,
    ) -> None:
        self.repository = repository or ProjectRepository()
        self.registry = registry or build_default_registry()
        self.validator = ProjectValidator(self.registry)
        self.compiler = JobCompiler(self.validator)
        self.supervisor = supervisor or SameHostSupervisor()
        self.project: Optional[ProjectDefinition] = None
        self.project_dir: Optional[Path] = None
        self.stage_index: Optional[StageIndex] = None
        self.dirty = False
        self.last_job: Optional[JobSpec] = None
        self.last_output_root: Optional[Path] = None
        self.migration_notice = ""

    def new_project(
        self,
        *,
        project_id: str,
        name: str,
        usd_path: str,
        output_root: str = "output",
    ) -> ProjectDefinition:
        self.project = ProjectDefinition(
            project_id=project_id,
            name=name,
            stage=StageReference(usd_path),
            sensors=[],
            variants=[
                VariantDefinition(
                    variant_id="full_scene",
                    strategy="full_scene",
                )
            ],
            modalities=[
                ModalityDefinition("rgb", "rgb"),
                ModalityDefinition("semantic_id", "semantic_id"),
                ModalityDefinition("semantic_color", "semantic_color"),
                ModalityDefinition("depth_linear", "depth_linear"),
                ModalityDefinition("depth_color", "depth_color"),
                ModalityDefinition("surface_normal", "surface_normal"),
                ModalityDefinition(
                    "surface_normal_color", "surface_normal_color"
                ),
                ModalityDefinition("instance_id", "instance_id"),
                ModalityDefinition("instance_color", "instance_color"),
                ModalityDefinition("point_cloud", "point_cloud"),
                ModalityDefinition("point_cloud_ply", "point_cloud_ply"),
            ],
            render=RenderProfile(),
            capture=CaptureSchedule(),
            output=OutputPolicy(root_dir=output_root),
        )
        self.project_dir = None
        self.stage_index = None
        self.dirty = True
        self.migration_notice = ""
        return self.project

    def open_project(self, project_dir: Path) -> ProjectDefinition:
        self.project = self.repository.load(project_dir)
        self.project_dir = Path(project_dir)
        self.stage_index = None
        source_version = self.repository.last_loaded_schema_version
        self.migration_notice = (
            f"Schema v{source_version} loaded as v{SCHEMA_VERSION}; the first save "
            "will preserve project.schema_v1.backup.json"
            if source_version < SCHEMA_VERSION
            else ""
        )
        self.dirty = source_version < SCHEMA_VERSION
        return self.project

    def save_project(self, project_dir: Optional[Path] = None) -> Path:
        project = self._require_project()
        destination = Path(project_dir) if project_dir is not None else self.project_dir
        if destination is None:
            raise ValueError("a destination is required for the first project save")
        self.repository.save(destination, project)
        self.project_dir = destination
        self.dirty = False
        return destination

    def save_project_as(self, project_dir: Path) -> Path:
        """Save the current editable state under a new project directory."""

        return self.save_project(Path(project_dir))

    def set_stage_index(self, stage_index: Optional[StageIndex]) -> None:
        self.stage_index = stage_index

    def get_sensor(self, sensor_id: str) -> SensorDefinition:
        return self._sensor(sensor_id)

    def get_variant(self, variant_id: str) -> VariantDefinition:
        return self._variant(variant_id)

    def discover_cameras(self) -> List[str]:
        return self.discover_sensors("pinhole_camera")

    def sensor_plugin_catalog(self) -> List[Dict[str, Any]]:
        result = []
        for manifest in self.registry.manifests("sensor"):
            plugin = self.registry.sensor(manifest.plugin_id)
            capabilities = getattr(plugin, "capabilities", lambda: None)()
            schema = getattr(plugin, "parameter_schema", lambda: {})()
            result.append(
                {
                    "manifest": manifest.to_dict(),
                    "capabilities": (
                        {} if capabilities is None else capabilities.to_dict()
                    ),
                    "parameter_schema": schema,
                }
            )
        return result

    def discover_sensors(self, plugin_id: Optional[str] = None) -> List[str]:
        if self.stage_index is None:
            return []
        plugin_ids = [plugin_id] if plugin_id else self.registry.sensor_ids()
        matches = set()
        for current_id in plugin_ids:
            plugin = self.registry.sensor(current_id)
            matches.update(
                prim.path
                for prim in self.stage_index.iter_prims()
                if plugin.matches_prim(prim)
            )
        return sorted(matches)

    def effective_sensor_preview(self, sensor_id: str) -> Dict[str, Any]:
        sensor = self._sensor(sensor_id)
        plugin = self.registry.sensor(sensor.plugin)
        return dict(plugin.compile_runtime_payload(sensor, self.stage_index))

    def add_camera_from_stage(
        self, prim_path: str, sensor_id: Optional[str] = None
    ) -> SensorDefinition:
        return self.add_sensor_from_stage(
            "pinhole_camera", prim_path, sensor_id=sensor_id
        )

    def add_sensor_from_stage(
        self,
        plugin_id: str,
        prim_path: str,
        sensor_id: Optional[str] = None,
    ) -> SensorDefinition:
        project = self._require_project()
        if self.stage_index is None:
            raise RuntimeError("a StageIndex is required to add a Stage sensor")
        prim = self.stage_index.require(prim_path)
        plugin = self.registry.sensor(plugin_id)
        if not plugin.matches_prim(prim):
            raise ValueError(
                f"Prim {prim_path} is not compatible with sensor plugin {plugin_id}"
            )
        resolved_id = sensor_id or self._unique_sensor_id(prim.name or plugin_id)
        sensor = plugin.definition_from_prim(resolved_id, prim)
        project.sensors.append(sensor)
        defaults = (
            ["point_cloud"]
            if plugin_id == "rtx_lidar"
            else ["rgb", "semantic_id", "semantic_color"]
        )
        known_modalities = {item.modality_id for item in project.modalities}
        for modality_id in defaults:
            if modality_id not in known_modalities:
                project.modalities.append(
                    ModalityDefinition(modality_id, modality_id)
                )
        for variant in project.variants:
            variant.modalities_by_sensor.setdefault(sensor.sensor_id, list(defaults))
        self.dirty = True
        return sensor

    def add_include_variant(
        self, variant_id: str, include_paths: List[str]
    ) -> VariantDefinition:
        project = self._require_project()
        variant = VariantDefinition(
            variant_id=variant_id,
            strategy="include_paths",
            include_paths=list(include_paths),
            modalities_by_sensor={
                sensor.sensor_id: ["semantic_id", "semantic_color"]
                for sensor in project.sensors
                if sensor.enabled
            },
        )
        project.variants.append(variant)
        self.dirty = True
        return variant

    def set_sensor_enabled(self, sensor_id: str, enabled: bool) -> SensorDefinition:
        sensor = self._sensor(sensor_id)
        sensor.enabled = bool(enabled)
        self.dirty = True
        return sensor

    def copy_sensor(
        self, sensor_id: str, new_sensor_id: Optional[str] = None
    ) -> SensorDefinition:
        project = self._require_project()
        source = self._sensor(sensor_id)
        copied = SensorDefinition(
            sensor_id=new_sensor_id or self._unique_sensor_id(sensor_id),
            plugin=source.plugin,
            prim_path=source.prim_path,
            enabled=source.enabled,
            stage_parameters=deepcopy(source.stage_parameters),
            parameters=deepcopy(source.parameters),
            parameter_sources=deepcopy(source.parameter_sources),
            plugin_version=source.plugin_version,
            backend=source.backend,
            sync_group_id=None,
        )
        if any(item.sensor_id == copied.sensor_id for item in project.sensors):
            raise ValueError(f"duplicate sensor_id: {copied.sensor_id}")
        project.sensors.append(copied)
        for variant in project.variants:
            if sensor_id in variant.modalities_by_sensor:
                variant.modalities_by_sensor[copied.sensor_id] = list(
                    variant.modalities_by_sensor[sensor_id]
                )
        self.dirty = True
        return copied

    def delete_sensor(self, sensor_id: str) -> None:
        project = self._require_project()
        self._sensor(sensor_id)
        project.sensors = [item for item in project.sensors if item.sensor_id != sensor_id]
        for variant in project.variants:
            variant.modalities_by_sensor.pop(sensor_id, None)
        for rig in project.rigs:
            rig.sensor_ids = [item for item in rig.sensor_ids if item != sensor_id]
        self.dirty = True

    def set_sensor_overrides(
        self, sensor_id: str, overrides: dict
    ) -> SensorDefinition:
        sensor = self._sensor(sensor_id)
        if not isinstance(overrides, dict):
            raise TypeError("sensor overrides must be a JSON object")
        plugin = self.registry.sensor(sensor.plugin)
        schema_method = getattr(plugin, "parameter_schema", None)
        if callable(schema_method):
            issues = parameter_schema_issues(
                overrides,
                schema_method(),
                path=f"sensors.{sensor_id}.overrides",
            )
            if issues:
                raise ValueError("; ".join(issues))
        sensor.parameters.update(deepcopy(overrides))
        for key in overrides:
            sensor.parameter_sources[str(key)] = "override"
        self.dirty = True
        return sensor

    def clear_sensor_overrides(
        self, sensor_id: str, parameter_names: List[str]
    ) -> SensorDefinition:
        sensor = self._sensor(sensor_id)
        for name in parameter_names:
            if sensor.parameter_sources.get(name) == "override":
                if name in sensor.stage_parameters:
                    sensor.parameters[name] = deepcopy(sensor.stage_parameters[name])
                    sensor.parameter_sources[name] = "stage"
                else:
                    sensor.parameters.pop(name, None)
                    sensor.parameter_sources.pop(name, None)
        self.dirty = True
        return sensor

    def add_rig(
        self,
        rig_id: str,
        sensor_ids: List[str],
        *,
        reference_frame_prim_path: Optional[str] = None,
    ) -> RigDefinition:
        project = self._require_project()
        if any(rig.rig_id == rig_id for rig in project.rigs):
            raise ValueError(f"duplicate rig_id: {rig_id}")
        known = {sensor.sensor_id for sensor in project.sensors}
        unknown = set(sensor_ids) - known
        if unknown:
            raise ValueError(f"unknown rig sensors: {sorted(unknown)}")
        rig = RigDefinition(
            rig_id=rig_id,
            sensor_ids=list(dict.fromkeys(sensor_ids)),
            reference_frame_prim_path=reference_frame_prim_path,
        )
        project.rigs.append(rig)
        for sensor_id in rig.sensor_ids:
            self._sensor(sensor_id).sync_group_id = rig_id
        self.dirty = True
        return rig

    def delete_rig(self, rig_id: str) -> None:
        project = self._require_project()
        rig = next((item for item in project.rigs if item.rig_id == rig_id), None)
        if rig is None:
            raise KeyError(f"unknown rig: {rig_id}")
        project.rigs = [item for item in project.rigs if item.rig_id != rig_id]
        for sensor_id in rig.sensor_ids:
            sensor = self._sensor(sensor_id)
            if sensor.sync_group_id == rig_id:
                sensor.sync_group_id = None
        self.dirty = True

    def set_variant_enabled(self, variant_id: str, enabled: bool) -> VariantDefinition:
        variant = self._variant(variant_id)
        variant.enabled = bool(enabled)
        self.dirty = True
        return variant

    def delete_variant(self, variant_id: str) -> None:
        project = self._require_project()
        self._variant(variant_id)
        project.variants = [
            item for item in project.variants if item.variant_id != variant_id
        ]
        self.dirty = True

    def set_modalities(
        self, variant_id: str, sensor_id: str, modality_ids: List[str]
    ) -> None:
        project = self._require_project()
        variant = self._variant(variant_id)
        sensor = self._sensor(sensor_id)
        enabled = {
            item.modality_id for item in project.modalities if item.enabled
        }
        supported = set(
            self.registry.sensor(sensor.plugin).supported_modalities()
        )
        unknown = set(modality_ids) - enabled
        unsupported = set(modality_ids) - supported
        if unknown:
            raise ValueError(f"unknown or disabled modalities: {sorted(unknown)}")
        if unsupported:
            raise ValueError(
                f"sensor {sensor_id} does not support: {sorted(unsupported)}"
            )
        variant.modalities_by_sensor[sensor_id] = list(dict.fromkeys(modality_ids))
        self.dirty = True

    def set_render_profile(
        self,
        *,
        renderer: str,
        resolution_width: int,
        resolution_height: int,
        warmup_frames: int,
        rt_subframes: int,
        spp_per_frame: int,
        total_spp: int,
        max_bounces: int,
        denoiser: bool,
        settings: Optional[Dict[str, Any]] = None,
    ) -> RenderProfile:
        project = self._require_project()
        updated = RenderProfile.from_dict(
            {
                "renderer": renderer,
                "resolution_width": resolution_width,
                "resolution_height": resolution_height,
                "warmup_frames": warmup_frames,
                "rt_subframes": rt_subframes,
                "spp_per_frame": spp_per_frame,
                "total_spp": total_spp,
                "max_bounces": max_bounces,
                "denoiser": denoiser,
                "settings": (
                    dict(project.render.settings)
                    if settings is None
                    else dict(settings)
                ),
            }
        )
        if project.render != updated:
            project.render = updated
            self.dirty = True
        return project.render

    def set_capture_schedule(
        self,
        *,
        physics_hz: int,
        capture_fps: int,
        start_frame: int,
        frame_count: int,
        capture_initial_frame: bool,
        segment_frames: int,
    ) -> CaptureSchedule:
        project = self._require_project()
        updated = CaptureSchedule.from_dict(
            {
                "physics_hz": physics_hz,
                "capture_fps": capture_fps,
                "start_frame": start_frame,
                "frame_count": frame_count,
                "capture_initial_frame": capture_initial_frame,
                "segment_frames": segment_frames,
            }
        )
        if project.capture != updated:
            project.capture = updated
            self.dirty = True
        return project.capture

    def set_execution_policy(
        self,
        *,
        segmentation_strategy: str,
        heartbeat_timeout_seconds: float,
        no_progress_timeout_seconds: float,
        segment_start_timeout_seconds: float,
        graceful_stop_timeout_seconds: float,
        telemetry_interval_seconds: float,
    ) -> ExecutionPolicy:
        """Update the lightweight runner policy stored with the project."""

        project = self._require_project()
        updated = ExecutionPolicy.from_dict(
            {
                "segmentation_strategy": segmentation_strategy,
                "heartbeat_timeout_seconds": heartbeat_timeout_seconds,
                "no_progress_timeout_seconds": no_progress_timeout_seconds,
                "segment_start_timeout_seconds": segment_start_timeout_seconds,
                "graceful_stop_timeout_seconds": graceful_stop_timeout_seconds,
                "telemetry_interval_seconds": telemetry_interval_seconds,
            }
        )
        if project.execution != updated:
            project.execution = updated
            self.dirty = True
        return project.execution

    def set_motion_spec(
        self,
        *,
        plugin: str,
        source_path: Optional[str],
        supports_absolute_seek: bool,
        options: Optional[Dict[str, Any]] = None,
    ) -> MotionSpec:
        project = self._require_project()
        normalized_source = None if not source_path else source_path
        updated = MotionSpec.from_dict(
            {
                "plugin": plugin,
                "source_path": normalized_source,
                "supports_absolute_seek": supports_absolute_seek,
                "options": dict(options or {}),
            }
        )
        if project.motion != updated:
            project.motion = updated
            self.dirty = True
        return project.motion

    def set_semantic_profile(
        self,
        *,
        mapping_path: Optional[str],
        label_attribute: str,
        background_id: int,
        options: Optional[Dict[str, Any]] = None,
    ) -> SemanticProfile:
        project = self._require_project()
        updated = SemanticProfile.from_dict(
            {
                "mapping_path": None if not mapping_path else mapping_path,
                "label_attribute": label_attribute,
                "background_id": background_id,
                "options": dict(options or {}),
            }
        )
        if project.semantics != updated:
            project.semantics = updated
            self.dirty = True
        return project.semantics

    def validate(self):
        return self.validator.validate(self._require_project(), self.stage_index)

    def preflight_summary(self) -> Dict[str, Any]:
        project = self._require_project()
        issues = list(self.validate())
        estimate = estimate_output(project)
        if self.stage_index is None:
            issues.append(
                ValidationIssue(
                    "stage.not_indexed",
                    "open or refresh the USD Stage before production capture",
                    "stage.usd_path",
                    hint="Studio uses the index to validate every configured Prim path",
                )
            )
        self._preflight_file(
            issues, project.stage.usd_path, "stage.usd_path", required=True
        )
        self._preflight_file(
            issues,
            project.motion.source_path,
            "motion.source_path",
            required=project.motion.plugin != "none",
        )
        self._preflight_file(
            issues,
            project.semantics.mapping_path,
            "semantics.mapping_path",
            required=False,
        )
        disk = self._preflight_output(issues, estimate.estimated_bytes)
        sensor_capabilities = []
        for sensor in project.sensors:
            if not sensor.enabled:
                continue
            plugin = self.registry.sensor(sensor.plugin)
            manifest = self.registry.manifest("sensor", sensor.plugin)
            capabilities_method = getattr(plugin, "capabilities", None)
            capabilities = (
                capabilities_method().to_dict()
                if callable(capabilities_method)
                else {}
            )
            sensor_capabilities.append(
                {
                    "sensor_id": sensor.sensor_id,
                    "plugin_id": sensor.plugin,
                    "plugin_version": manifest.plugin_version,
                    "backend": sensor.backend,
                    "capabilities": capabilities,
                }
            )
        return {
            "can_run": not any(issue.severity == "error" for issue in issues),
            "stage_indexed": self.stage_index is not None,
            "project_saved": self.project_dir is not None,
            "issues": [
                {
                    "code": issue.code,
                    "severity": issue.severity,
                    "path": issue.path,
                    "message": issue.message,
                    "hint": issue.hint,
                }
                for issue in issues
            ],
            "estimate": estimate.to_dict(),
            "disk": disk,
            "sensor_capabilities": sensor_capabilities,
        }

    def _preflight_file(
        self,
        issues: List[ValidationIssue],
        value: Optional[str],
        field_path: str,
        *,
        required: bool,
    ) -> None:
        if not value:
            if required:
                issues.append(
                    ValidationIssue(
                        "preflight.path_required",
                        "a file path is required",
                        field_path,
                    )
                )
            return
        if ProjectPathResolver.is_uri(value):
            return
        base = self.project_dir or Path.cwd()
        resolved = Path(str(ProjectPathResolver.resolve(value, base)))
        if not resolved.is_file():
            issues.append(
                ValidationIssue(
                    "preflight.file_missing",
                    f"file does not exist on this host: {resolved}",
                    field_path,
                )
            )

    def _preflight_output(
        self, issues: List[ValidationIssue], estimated_bytes: int
    ) -> Dict[str, Any]:
        project = self._require_project()
        base = self.project_dir or Path.cwd()
        value = project.output.root_dir
        resolved_value = ProjectPathResolver.resolve(value, base)
        if resolved_value is None or ProjectPathResolver.is_uri(resolved_value):
            issues.append(
                ValidationIssue(
                    "preflight.output_path",
                    "output root must be a local filesystem path",
                    "output.root_dir",
                )
            )
            return {"path": str(resolved_value or ""), "available": False}
        output_path = Path(resolved_value)
        if output_path.exists() and not output_path.is_dir():
            issues.append(
                ValidationIssue(
                    "preflight.output_not_directory",
                    "output root exists but is not a directory",
                    "output.root_dir",
                )
            )
            return {"path": str(output_path), "available": False}
        existing = output_path
        while not existing.exists() and existing != existing.parent:
            existing = existing.parent
        writable = existing.is_dir() and os.access(str(existing), os.W_OK)
        if not writable:
            issues.append(
                ValidationIssue(
                    "preflight.output_not_writable",
                    f"output root cannot be created or written: {output_path}",
                    "output.root_dir",
                )
            )
            return {"path": str(output_path), "available": False}
        usage = shutil.disk_usage(existing)
        if usage.free < estimated_bytes:
            issues.append(
                ValidationIssue(
                    "preflight.disk_space",
                    (
                        f"estimated output requires {estimated_bytes} bytes but "
                        f"only {usage.free} bytes are free"
                    ),
                    "output.root_dir",
                )
            )
        return {
            "path": str(output_path),
            "checked_at": str(existing),
            "available": True,
            "writable": writable,
            "free_bytes": usage.free,
            "estimated_bytes": estimated_bytes,
        }

    def list_jobs(self) -> List[Dict[str, Any]]:
        """List compiled and submitted jobs without mutating their status."""

        project = self._require_project()
        candidates: Dict[str, Path] = {}
        if self.project_dir is not None:
            for path in (self.project_dir / "jobs").glob("*/job_spec.json"):
                candidates[path.parent.name] = path
        output_root = Path(project.output.root_dir)
        if not output_root.is_absolute() and self.project_dir is not None:
            output_root = self.project_dir / output_root
        if output_root.exists():
            for path in output_root.glob("*/job_spec.json"):
                candidates[path.parent.name] = path

        jobs: List[Dict[str, Any]] = []
        for job_id, spec_path in candidates.items():
            try:
                spec = JobSpec.from_dict(read_json(spec_path))
                status_path = output_root / job_id / "status.json"
                if status_path.is_file():
                    status = StatusStore(status_path).read()
                    state = status.state
                    progress = f"{status.frame_current}/{status.frame_total}"
                    message = status.message
                    segment_progress = (
                        f"{status.segment_current}/{status.segment_total}"
                    )
                    current_segment_id = status.current_segment_id
                    gpu_memory_used_mb = status.gpu_memory_used_mb
                    failure_report_path = status.failure_report_path
                else:
                    state = "compiled"
                    progress = "0/0"
                    message = "JobSpec compiled but not submitted"
                    segment_progress = "0/0"
                    current_segment_id = None
                    gpu_memory_used_mb = None
                    failure_report_path = None
                jobs.append(
                    {
                        "job_id": job_id,
                        "compiled_at_utc": spec.compiled_at_utc,
                        "state": state,
                        "progress": progress,
                        "segment_progress": segment_progress,
                        "current_segment_id": current_segment_id,
                        "gpu_memory_used_mb": gpu_memory_used_mb,
                        "failure_report_path": failure_report_path,
                        "message": message,
                        "job_spec_path": str(spec_path),
                        "output_dir": str(output_root / job_id),
                    }
                )
            except Exception as exc:
                jobs.append(
                    {
                        "job_id": job_id,
                        "compiled_at_utc": "",
                        "state": "invalid",
                        "progress": "0/0",
                        "segment_progress": "0/0",
                        "current_segment_id": None,
                        "gpu_memory_used_mb": None,
                        "failure_report_path": None,
                        "message": str(exc),
                        "job_spec_path": str(spec_path),
                        "output_dir": str(output_root / job_id),
                    }
                )
        return sorted(
            jobs,
            key=lambda item: (str(item["compiled_at_utc"]), str(item["job_id"])),
            reverse=True,
        )

    def compile_job(self, job_id: Optional[str] = None) -> JobSpec:
        project = self._require_project()
        source = "" if self.project_dir is None else str(self.project_dir)
        job = self.compiler.compile(
            project,
            source_project_path=source,
            stage_index=self.stage_index,
            job_id=job_id,
        )
        if self.project_dir is not None:
            job_dir = self.project_dir / "jobs" / job.job_id
            atomic_write_json(job_dir / "job_spec.json", job.to_dict())
        self.last_job = job
        return job

    def run_headless(self, job_id: Optional[str] = None) -> JobStatus:
        """Compile, submit, and detach a same-host headless Runtime job."""

        job = self.compile_job(job_id=job_id)
        output_root = SameHostSupervisor.job_dir(job).parent
        self.supervisor.submit(job)
        status = self.supervisor.start(job.job_id, output_root)
        self.last_job = job
        self.last_output_root = output_root
        return status

    def job_status(
        self,
        job_id: Optional[str] = None,
        output_root: Optional[Path] = None,
    ) -> JobStatus:
        resolved_id, resolved_root = self._resolve_job_location(job_id, output_root)
        return self.supervisor.status(resolved_id, resolved_root)

    def stop_job(
        self,
        job_id: Optional[str] = None,
        output_root: Optional[Path] = None,
    ) -> JobStatus:
        resolved_id, resolved_root = self._resolve_job_location(job_id, output_root)
        return self.supervisor.stop(resolved_id, resolved_root)

    def resume_job(
        self,
        job_id: Optional[str] = None,
        output_root: Optional[Path] = None,
    ) -> JobStatus:
        resolved_id, resolved_root = self._resolve_job_location(job_id, output_root)
        return self.supervisor.resume(resolved_id, resolved_root)

    def tail_job_logs(
        self,
        job_id: Optional[str] = None,
        output_root: Optional[Path] = None,
        lines: int = 50,
    ) -> List[str]:
        resolved_id, resolved_root = self._resolve_job_location(job_id, output_root)
        return self.supervisor.tail_logs(resolved_id, resolved_root, lines)

    def list_segments(
        self,
        job_id: Optional[str] = None,
        output_root: Optional[Path] = None,
    ) -> List[Dict[str, Any]]:
        """Return durable per-segment state for Studio and diagnostics."""

        resolved_id, resolved_root = self._resolve_job_location(job_id, output_root)
        segment_root = resolved_root / resolved_id / "segments"
        result: List[Dict[str, Any]] = []
        for status_path in sorted(segment_root.glob("*/status.json")):
            try:
                status = SegmentStatusStore(status_path).read()
                item = status.to_dict()
                spec_path = status_path.parent / "segment_spec.json"
                if spec_path.is_file():
                    spec = read_json(spec_path)
                    item.update(
                        {
                            "start_frame": spec.get("start_frame"),
                            "frame_count": spec.get("frame_count"),
                            "end_frame_exclusive": spec.get("end_frame_exclusive"),
                            "motion_positioning": spec.get("motion_positioning"),
                        }
                    )
                item["status_path"] = str(status_path)
                result.append(item)
            except Exception as exc:
                result.append(
                    {
                        "segment_id": status_path.parent.name,
                        "state": "invalid",
                        "message": str(exc),
                        "status_path": str(status_path),
                    }
                )
        return result

    def read_failure_report(
        self,
        job_id: Optional[str] = None,
        output_root: Optional[Path] = None,
    ) -> Optional[Dict[str, Any]]:
        """Load the structured failure report when the last run failed."""

        resolved_id, resolved_root = self._resolve_job_location(job_id, output_root)
        path = resolved_root / resolved_id / "failure_report.json"
        if not path.is_file():
            return None
        report = read_json(path)
        report["path"] = str(path)
        return report

    def _resolve_job_location(
        self, job_id: Optional[str], output_root: Optional[Path]
    ):
        resolved_id = job_id or (
            None if self.last_job is None else self.last_job.job_id
        )
        resolved_root = (
            Path(output_root)
            if output_root is not None
            else self.last_output_root
        )
        if not resolved_id:
            raise ValueError("a job_id is required")
        if resolved_root is None:
            raise ValueError("an output_root is required")
        return resolved_id, resolved_root

    def _unique_sensor_id(self, base: str) -> str:
        project = self._require_project()
        normalized = "".join(
            character.lower() if character.isalnum() else "_"
            for character in base
        ).strip("_") or "camera"
        used = {sensor.sensor_id for sensor in project.sensors}
        candidate = normalized
        suffix = 2
        while candidate in used:
            candidate = f"{normalized}_{suffix}"
            suffix += 1
        return candidate

    def _sensor(self, sensor_id: str) -> SensorDefinition:
        project = self._require_project()
        for sensor in project.sensors:
            if sensor.sensor_id == sensor_id:
                return sensor
        raise KeyError(f"unknown sensor: {sensor_id}")

    def _variant(self, variant_id: str) -> VariantDefinition:
        project = self._require_project()
        for variant in project.variants:
            if variant.variant_id == variant_id:
                return variant
        raise KeyError(f"unknown variant: {variant_id}")

    def _require_project(self) -> ProjectDefinition:
        if self.project is None:
            raise RuntimeError("no project is open")
        return self.project
