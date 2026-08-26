"""Compile editable projects into immutable, integrity-checked JobSpecs."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from semantic_world_v04.core.errors import ValidationFailed
from semantic_world_v04.core.models import JobSpec, ProjectDefinition, SCHEMA_VERSION
from semantic_world_v04.core.serde import content_sha256
from semantic_world_v04.project.paths import ProjectPathResolver
from semantic_world_v04.stage.index import StageIndex

from .validator import ProjectValidator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class JobCompiler:
    def __init__(self, validator: Optional[ProjectValidator] = None) -> None:
        self.validator = validator or ProjectValidator()

    def compile(
        self,
        project: ProjectDefinition,
        *,
        source_project_path: str = "",
        stage_index: Optional[StageIndex] = None,
        job_id: Optional[str] = None,
        compiled_at_utc: Optional[str] = None,
    ) -> JobSpec:
        issues = self.validator.validate(project, stage_index)
        blocking = [issue for issue in issues if issue.severity == "error"]
        if blocking:
            raise ValidationFailed(blocking)

        # Round-trip creates an isolated snapshot and re-applies strict parsing.
        snapshot = ProjectDefinition.from_dict(project.to_dict())
        snapshot.schema_version = SCHEMA_VERSION
        if source_project_path:
            project_dir = Path(source_project_path)
            snapshot.stage.usd_path = str(
                ProjectPathResolver.resolve(snapshot.stage.usd_path, project_dir)
            )
            if snapshot.motion.source_path:
                snapshot.motion.source_path = str(
                    ProjectPathResolver.resolve(
                        snapshot.motion.source_path, project_dir
                    )
                )
        for sensor in snapshot.sensors:
            if not sensor.enabled:
                continue
            plugin = self.validator.registry.sensor(sensor.plugin)
            manifest = self.validator.registry.manifest("sensor", sensor.plugin)
            payload = plugin.compile_runtime_payload(sensor, stage_index)
            sensor.plugin_version = str(
                payload.get("plugin_version", sensor.plugin_version or manifest.plugin_version)
            )
            sensor.stage_parameters = dict(
                payload.get("stage_parameters", sensor.stage_parameters)
            )
            sensor.parameters = dict(payload.get("parameters", {}))
            sensor.parameter_sources = dict(
                payload.get("parameter_sources", {})
            )
            sensor.backend = str(payload.get("backend", sensor.backend))
            sensor.sync_group_id = payload.get(
                "sync_group_id", sensor.sync_group_id or sensor.sensor_id
            )
        for modality in snapshot.modalities:
            if modality.enabled:
                manifest = self.validator.registry.manifest(
                    "modality", modality.plugin
                )
                if not modality.plugin_version:
                    modality.plugin_version = manifest.plugin_version
        rig_owner = {
            sensor_id: rig.rig_id
            for rig in snapshot.rigs
            if rig.enabled
            for sensor_id in rig.sensor_ids
        }
        for sensor in snapshot.sensors:
            if sensor.sensor_id in rig_owner:
                sensor.sync_group_id = rig_owner[sensor.sensor_id]
        digest_payload = {
            "schema_version": SCHEMA_VERSION,
            "source_project_path": source_project_path,
            "project": snapshot.to_dict(),
        }
        digest = content_sha256(digest_payload)
        timestamp = compiled_at_utc or utc_now()
        resolved_job_id = job_id or (
            "job-"
            + timestamp.replace("-", "").replace(":", "").replace(".", "")[:15]
            + "-"
            + digest[:12]
        )
        return JobSpec(
            schema_version=SCHEMA_VERSION,
            job_id=resolved_job_id,
            compiled_at_utc=timestamp,
            source_project_path=source_project_path,
            project=snapshot,
            content_digest=digest,
        )

    @staticmethod
    def verify(job_spec: JobSpec) -> bool:
        payload = {
            "schema_version": job_spec.schema_version,
            "source_project_path": job_spec.source_project_path,
            "project": job_spec.project.to_dict(),
        }
        expected = content_sha256(
            payload
        )
        if expected == job_spec.content_digest:
            return True
        candidates = [dict(payload["project"])]
        for optional_key in ("execution", "rigs"):
            candidates += [
                {key: value for key, value in candidate.items() if key != optional_key}
                for candidate in list(candidates)
            ]
        for candidate in list(candidates):
            legacy = dict(candidate)
            legacy["sensors"] = [
                {
                    key: value
                    for key, value in sensor.items()
                    if key not in {"plugin_version", "backend", "sync_group_id"}
                }
                for sensor in candidate.get("sensors", [])
            ]
            legacy["modalities"] = [
                {
                    key: value
                    for key, value in modality.items()
                    if key != "plugin_version"
                }
                for modality in candidate.get("modalities", [])
            ]
            candidates.append(legacy)
        return any(
            content_sha256(
                {
                    "schema_version": job_spec.schema_version,
                    "source_project_path": job_spec.source_project_path,
                    "project": candidate,
                }
            )
            == job_spec.content_digest
            for candidate in candidates
        )
