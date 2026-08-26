"""Revisioned project repository with an atomically replaced manifest."""

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping

from semantic_world_v04.core.errors import ProjectIOError, SchemaError
from semantic_world_v04.core.models import (
    COMPATIBLE_SCHEMA_VERSIONS,
    ProjectDefinition,
    SCHEMA_VERSION,
)
from semantic_world_v04.core.serde import (
    content_sha256,
    expect_int,
    expect_mapping,
    expect_string,
    pretty_json,
    strict_keys,
    to_data,
)

_COMPONENT_FILES = {
    "stage": "stage.json",
    "sensors": "sensors.json",
    "variants": "variants.json",
    "modalities": "modalities.json",
    "render": "render.json",
    "capture": "capture.json",
    "motion": "motion.json",
    "semantics": "semantics.json",
    "output": "output.json",
    "execution": "execution.json",
    "rigs": "rigs.json",
}
_V042_COMPONENT_KEYS = set(_COMPONENT_FILES) - {"rigs"}
_V041_COMPONENT_KEYS = _V042_COMPONENT_KEYS - {"execution"}
_SUPPORTED_COMPONENT_SETS = {
    frozenset(_COMPONENT_FILES),
    frozenset(_V042_COMPONENT_KEYS),
    frozenset(_V041_COMPONENT_KEYS),
}


class ProjectRepository:
    """Persist editable projects without exposing half-written component sets."""

    manifest_name = "project.json"
    revisions_dir_name = ".revisions"

    def __init__(self) -> None:
        self.last_loaded_schema_version = SCHEMA_VERSION

    def save(self, project_dir: Path, project: ProjectDefinition) -> None:
        project_dir = Path(project_dir)
        project_dir.mkdir(parents=True, exist_ok=True)
        self._backup_legacy_manifest(project_dir)
        project.schema_version = SCHEMA_VERSION
        project_data = project.to_dict()
        revision = content_sha256(project_data)
        revisions_root = project_dir / self.revisions_dir_name
        revisions_root.mkdir(parents=True, exist_ok=True)
        revision_dir = revisions_root / revision

        if not revision_dir.exists():
            temp_dir = Path(
                tempfile.mkdtemp(prefix=f".{revision}.", dir=str(revisions_root))
            )
            try:
                self._write_revision(temp_dir, project)
                os.replace(str(temp_dir), str(revision_dir))
            except Exception as exc:
                shutil.rmtree(temp_dir, ignore_errors=True)
                if isinstance(exc, ProjectIOError):
                    raise
                raise ProjectIOError(f"failed to write project revision: {exc}") from exc

        components = {
            key: f"{self.revisions_dir_name}/{revision}/{filename}"
            for key, filename in _COMPONENT_FILES.items()
        }
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "project_id": project.project_id,
            "name": project.name,
            "description": project.description,
            "revision": revision,
            "components": components,
        }
        self._atomic_write_json(project_dir / self.manifest_name, manifest)

    def load(self, project_dir: Path) -> ProjectDefinition:
        project_dir = Path(project_dir)
        manifest_path = project_dir / self.manifest_name
        try:
            manifest = self._read_json(manifest_path)
            data = expect_mapping(manifest, "project_manifest")
            strict_keys(
                data,
                allowed={
                    "schema_version",
                    "project_id",
                    "name",
                    "description",
                    "revision",
                    "components",
                },
                required={
                    "schema_version",
                    "project_id",
                    "name",
                    "revision",
                    "components",
                },
                path="project_manifest",
            )
            version = expect_int(data["schema_version"], "project_manifest.schema_version")
            if version not in COMPATIBLE_SCHEMA_VERSIONS:
                raise SchemaError(
                    f"unsupported schema_version {version}; supported versions are "
                    f"{sorted(COMPATIBLE_SCHEMA_VERSIONS)}",
                    "project_manifest.schema_version",
                )
            components = expect_mapping(data["components"], "project_manifest.components")
            component_keys = set(components)
            if frozenset(component_keys) not in _SUPPORTED_COMPONENT_SETS:
                raise SchemaError(
                    "component set does not match the v04 schema",
                    "project_manifest.components",
                )
            revision = expect_string(data["revision"], "project_manifest.revision")
            assembled: Dict[str, Any] = {
                "schema_version": version,
                "project_id": expect_string(
                    data["project_id"], "project_manifest.project_id"
                ),
                "name": expect_string(data["name"], "project_manifest.name"),
                "description": expect_string(
                    data.get("description", ""),
                    "project_manifest.description",
                    allow_empty=True,
                ),
            }
            for key in _COMPONENT_FILES:
                if key not in components:
                    continue
                relative = expect_string(
                    components[key], f"project_manifest.components.{key}"
                )
                component_path = self._safe_component_path(project_dir, relative)
                component_doc = expect_mapping(
                    self._read_json(component_path), f"component.{key}"
                )
                strict_keys(
                    component_doc,
                    allowed={"schema_version", key},
                    required={"schema_version", key},
                    path=f"component.{key}",
                )
                component_version = expect_int(
                    component_doc["schema_version"],
                    f"component.{key}.schema_version",
                )
                if component_version != version:
                    raise SchemaError(
                        "component schema_version differs from manifest",
                        f"component.{key}.schema_version",
                    )
                assembled[key] = component_doc[key]
            project = ProjectDefinition.from_dict(assembled)
            project_data = project.to_dict()
            digest_matches = content_sha256(project_data) == revision
            if not digest_matches and (
                "execution" not in components or "rigs" not in components
            ):
                candidates = [dict(project_data)]
                for optional_key in ("execution", "rigs"):
                    if optional_key not in components:
                        candidates += [
                            {
                                key: value
                                for key, value in candidate.items()
                                if key != optional_key
                            }
                            for candidate in list(candidates)
                        ]
                for candidate in list(candidates):
                    legacy = dict(candidate)
                    legacy["sensors"] = [
                        {
                            field: field_value
                            for field, field_value in sensor.items()
                            if field
                            not in {"plugin_version", "backend", "sync_group_id"}
                        }
                        for sensor in candidate.get("sensors", [])
                    ]
                    legacy["modalities"] = [
                        {
                            field: field_value
                            for field, field_value in modality.items()
                            if field != "plugin_version"
                        }
                        for modality in candidate.get("modalities", [])
                    ]
                    candidates.append(legacy)
                digest_matches = any(
                    content_sha256(candidate) == revision for candidate in candidates
                )
            if not digest_matches:
                raise ProjectIOError(
                    "project revision digest does not match component contents"
                )
            self.last_loaded_schema_version = version
            if version < SCHEMA_VERSION:
                project.schema_version = SCHEMA_VERSION
                for sensor in project.sensors:
                    if sensor.sync_group_id is None:
                        sensor.sync_group_id = sensor.sensor_id
            return project
        except (ProjectIOError, SchemaError):
            raise
        except FileNotFoundError as exc:
            raise ProjectIOError(f"missing project file: {exc.filename}") from exc
        except json.JSONDecodeError as exc:
            raise ProjectIOError(
                f"invalid JSON in {exc.doc[:0] or manifest_path}: {exc}"
            ) from exc
        except OSError as exc:
            raise ProjectIOError(f"failed to load project: {exc}") from exc

    def _write_revision(self, revision_dir: Path, project: ProjectDefinition) -> None:
        data = project.to_dict()
        for key, filename in _COMPONENT_FILES.items():
            self._atomic_write_json(
                revision_dir / filename,
                {"schema_version": SCHEMA_VERSION, key: data[key]},
            )

    def _backup_legacy_manifest(self, project_dir: Path) -> None:
        manifest_path = project_dir / self.manifest_name
        backup_path = project_dir / "project.schema_v1.backup.json"
        if not manifest_path.is_file() or backup_path.exists():
            return
        try:
            current = expect_mapping(self._read_json(manifest_path), "project_manifest")
            version = expect_int(
                current.get("schema_version", SCHEMA_VERSION),
                "project_manifest.schema_version",
            )
            if version < SCHEMA_VERSION:
                shutil.copy2(manifest_path, backup_path)
        except (OSError, SchemaError, json.JSONDecodeError) as exc:
            raise ProjectIOError(
                f"failed to preserve legacy project manifest: {exc}"
            ) from exc

    @staticmethod
    def _safe_component_path(project_dir: Path, relative: str) -> Path:
        candidate = (project_dir / relative).resolve()
        root = project_dir.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ProjectIOError(
                f"component path escapes the project directory: {relative}"
            ) from exc
        return candidate

    @staticmethod
    def _read_json(path: Path) -> Any:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)

    @staticmethod
    def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(pretty_json(to_data(value)))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, path)
        except Exception as exc:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise ProjectIOError(f"failed to atomically write {path}: {exc}") from exc
