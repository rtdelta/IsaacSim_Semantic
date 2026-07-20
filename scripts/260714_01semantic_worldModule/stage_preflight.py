"""Read-only preflight checks for stage assets, semantics, cameras, and physics."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence


def file_record(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).resolve()
    record: dict[str, Any] = {"path": str(resolved), "exists": resolved.is_file()}
    if not resolved.is_file():
        return record
    digest = hashlib.sha256()
    with resolved.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    stat = resolved.stat()
    record.update(
        {
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
            "sha256": digest.hexdigest(),
        }
    )
    return record


@dataclass(frozen=True)
class PreflightIssue:
    severity: str
    code: str
    message: str
    prim_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "prim_path": self.prim_path,
        }


@dataclass
class PreflightReport:
    issues: list[PreflightIssue] = field(default_factory=list)
    layers: list[dict[str, Any]] = field(default_factory=list)
    external_assets: list[dict[str, Any]] = field(default_factory=list)
    semantic_prim_count: int = 0

    @property
    def errors(self) -> list[PreflightIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[PreflightIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    def add(self, severity: str, code: str, message: str, prim_path: str | None = None) -> None:
        if severity not in {"error", "warning", "info"}:
            raise ValueError(f"Invalid preflight severity: {severity}")
        self.issues.append(
            PreflightIssue(
                severity=severity,
                code=code,
                message=message,
                prim_path=prim_path,
            )
        )

    def raise_if_blocking(self, strict: bool) -> None:
        if strict and self.errors:
            summary = "; ".join(
                f"{issue.code}{' ' + issue.prim_path if issue.prim_path else ''}: {issue.message}"
                for issue in self.errors
            )
            raise RuntimeError(f"Stage preflight failed: {summary}")

    def raise_if_unusable(self) -> None:
        """Block errors that make capture impossible even in diagnostic mode."""
        fatal_codes = {
            "SOURCE_STAGE_MISSING",
            "MAPPING_MISSING",
            "CAMERA_INVALID",
            "SEMANTICS_MISSING",
        }
        fatal = [issue for issue in self.errors if issue.code in fatal_codes]
        if fatal:
            summary = "; ".join(f"{issue.code}: {issue.message}" for issue in fatal)
            raise RuntimeError(f"Stage is not usable for semantic capture: {summary}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": not self.errors,
            "semantic_prim_count": int(self.semantic_prim_count),
            "issues": [issue.to_dict() for issue in self.issues],
            "layers": list(self.layers),
            "external_assets": list(self.external_assets),
        }


def _attribute_value(prim: Any, name: str) -> tuple[bool, Any]:
    attr = prim.GetAttribute(name)
    if not attr or not attr.IsValid() or not attr.HasAuthoredValueOpinion():
        return False, None
    try:
        return True, attr.Get()
    except Exception as exc:  # USD raises several runtime-specific exception types.
        return True, exc


def _numeric_values(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return []


class StagePreflight:
    """Collect diagnostics without authoring any changes to the USD stage."""

    def __init__(
        self,
        stage: Any,
        source_stage: str | Path,
        mapping_path: str | Path,
        camera_path: str,
        cab_root: str,
        require_camera_below_cab: bool,
        joint_specs: Sequence[Any] = (),
    ) -> None:
        self._stage = stage
        self._source_stage = Path(source_stage).resolve()
        self._mapping_path = Path(mapping_path).resolve()
        self._camera_path = camera_path
        self._cab_root = cab_root
        self._require_camera_below_cab = bool(require_camera_below_cab)
        self._joint_specs = tuple(joint_specs)

    def _check_files(self, report: PreflightReport) -> None:
        for code, path in (
            ("SOURCE_STAGE_MISSING", self._source_stage),
            ("MAPPING_MISSING", self._mapping_path),
        ):
            record = file_record(path)
            if not record["exists"]:
                report.add("error", code, f"File does not exist: {path}")

    def _check_layers_and_dependencies(self, report: PreflightReport) -> None:
        try:
            layer_stack = self._stage.GetLayerStack(True)
        except TypeError:
            layer_stack = self._stage.GetLayerStack()
        for layer in layer_stack:
            identifier = str(getattr(layer, "identifier", ""))
            real_path = str(getattr(layer, "realPath", "") or "")
            record: dict[str, Any] = {
                "identifier": identifier,
                "real_path": real_path,
                "anonymous": bool(getattr(layer, "anonymous", False)),
            }
            if real_path:
                record.update(file_record(real_path))
            report.layers.append(record)

        try:
            from pxr import Ar, UsdUtils

            root_identifier = str(self._stage.GetRootLayer().identifier)
            layers, assets, unresolved = UsdUtils.ComputeAllDependencies(root_identifier)
            known = set()
            for asset in assets:
                asset_path = str(asset)
                if asset_path in known:
                    continue
                known.add(asset_path)
                resolved = str(Ar.GetResolver().Resolve(asset_path) or "")
                exists = bool(resolved and Path(resolved).is_file())
                record = {
                    "asset_path": asset_path,
                    "resolved_path": resolved,
                    "exists": exists,
                }
                if exists:
                    record.update(file_record(resolved))
                report.external_assets.append(record)
                if not exists:
                    report.add("error", "ASSET_UNRESOLVED", f"Asset could not be resolved: {asset_path}")
            for unresolved_path in unresolved:
                report.add(
                    "error",
                    "ASSET_UNRESOLVED",
                    f"Dependency could not be resolved: {unresolved_path}",
                )
            _ = layers
        except Exception as exc:
            report.add(
                "warning",
                "DEPENDENCY_SCAN_FAILED",
                f"USD dependency scan was not available: {exc}",
            )

    def _check_camera_and_semantics(self, report: PreflightReport) -> None:
        from pxr import UsdGeom

        camera_prim = self._stage.GetPrimAtPath(self._camera_path)
        if not camera_prim.IsValid() or not camera_prim.IsA(UsdGeom.Camera):
            report.add(
                "error",
                "CAMERA_INVALID",
                "Camera prim is missing or is not a UsdGeom.Camera",
                self._camera_path,
            )
        elif self._require_camera_below_cab and not self._camera_path.startswith(
            self._cab_root.rstrip("/") + "/"
        ):
            report.add(
                "error",
                "CAMERA_PARENT_INVALID",
                f"Camera is not below configured cab root {self._cab_root}",
                self._camera_path,
            )

        count = 0
        for prim in self._stage.Traverse():
            try:
                if any(
                    str(schema).startswith("SemanticsLabelsAPI")
                    for schema in prim.GetAppliedSchemas()
                ):
                    count += 1
            except Exception as exc:
                report.add(
                    "warning",
                    "SEMANTICS_INSPECTION_FAILED",
                    f"Could not inspect applied schemas: {exc}",
                    str(prim.GetPath()),
                )
        report.semantic_prim_count = count
        if count == 0:
            report.add("error", "SEMANTICS_MISSING", "No SemanticsLabelsAPI labels were found")

    def _check_joint_and_body(self, report: PreflightReport, spec: Any) -> None:
        joint_path = str(getattr(spec, "path", ""))
        body_path = str(getattr(spec, "body_path", ""))
        joint = self._stage.GetPrimAtPath(joint_path)
        if not joint.IsValid() or joint.GetTypeName() != "PhysicsRevoluteJoint":
            report.add("error", "JOINT_INVALID", "Expected PhysicsRevoluteJoint", joint_path)
        body = self._stage.GetPrimAtPath(body_path)
        if not body.IsValid():
            report.add("error", "BODY_INVALID", "Controlled body prim is missing", body_path)
            return

        has_mass, mass = _attribute_value(body, "physics:mass")
        if has_mass:
            values = _numeric_values(mass)
            if not values or not math.isfinite(values[0]) or values[0] <= 0:
                report.add(
                    "error",
                    "MASS_INVALID",
                    f"Authored mass must be finite and positive, got {mass!r}",
                    body_path,
                )
        else:
            report.add(
                "warning",
                "MASS_NOT_AUTHORED",
                "No authored mass was found; PhysX must derive it from valid collision geometry",
                body_path,
            )

        has_inertia, inertia = _attribute_value(body, "physics:diagonalInertia")
        if has_inertia:
            values = _numeric_values(inertia)
            if len(values) != 3 or any(not math.isfinite(value) or value <= 0 for value in values):
                report.add(
                    "error",
                    "INERTIA_INVALID",
                    f"Authored diagonal inertia must contain three positive values, got {inertia!r}",
                    body_path,
                )

        has_rotate, rotate_value = _attribute_value(body, "xformOp:rotateZYX")
        if has_rotate and isinstance(rotate_value, Exception):
            report.add(
                "error",
                "XFORM_VALUE_INVALID",
                f"Could not read xformOp:rotateZYX: {rotate_value}",
                body_path,
            )

    def run(self) -> PreflightReport:
        report = PreflightReport()
        self._check_files(report)
        self._check_layers_and_dependencies(report)
        self._check_camera_and_semantics(report)
        for spec in self._joint_specs:
            self._check_joint_and_body(report, spec)
        return report
