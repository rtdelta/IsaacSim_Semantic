"""Read-only validation and discovery for compatible excavator USD stages."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .config import ProjectConfig


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str
    prim_path: str = ""

    def format(self) -> str:
        location = f" [{self.prim_path}]" if self.prim_path else ""
        return f"{self.severity.upper()} {self.code}{location}: {self.message}"


@dataclass
class StageValidationReport:
    articulation_root_path: str | None = None
    root_body_path: str | None = None
    joint_paths: dict[str, str] = field(default_factory=dict)
    dof_names: dict[str, str] = field(default_factory=dict)
    body_paths: tuple[str, ...] = ()
    limits_degrees: dict[str, tuple[float, float]] = field(default_factory=dict)
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def require_valid(self) -> "StageValidationReport":
        if not self.ok:
            details = "\n".join(issue.format() for issue in self.errors)
            raise RuntimeError(f"Stage is not compatible with direct articulation control:\n{details}")
        return self


def validate_stage(stage: Any, config: ProjectConfig) -> StageValidationReport:
    """Discover and validate a fixed-base, four-revolute-joint articulation."""

    from pxr import UsdPhysics

    report = StageValidationReport()
    if stage is None:
        report.issues.append(ValidationIssue("error", "NO_STAGE", "No USD stage is open"))
        return report

    prims = [prim for prim in stage.Traverse() if prim.IsValid()]
    root_candidates = [prim for prim in prims if prim.HasAPI(UsdPhysics.ArticulationRootAPI)]
    root_prim = None
    if config.articulation_root_path:
        candidate = stage.GetPrimAtPath(config.articulation_root_path)
        if not candidate.IsValid() or not candidate.HasAPI(UsdPhysics.ArticulationRootAPI):
            report.issues.append(
                ValidationIssue(
                    "error",
                    "INVALID_ROOT_HINT",
                    "Configured path is missing PhysicsArticulationRootAPI",
                    config.articulation_root_path,
                )
            )
        else:
            root_prim = candidate
    elif len(root_candidates) == 1:
        root_prim = root_candidates[0]
    elif not root_candidates:
        report.issues.append(
            ValidationIssue("error", "MISSING_ROOT", "No PhysicsArticulationRootAPI was found")
        )
    else:
        report.issues.append(
            ValidationIssue(
                "error",
                "AMBIGUOUS_ROOT",
                f"Found {len(root_candidates)} articulation roots; set articulation_root_path in the profile",
            )
        )

    root_body_path: str | None = None
    if root_prim is not None:
        report.articulation_root_path = str(root_prim.GetPath())
        if root_prim.IsA(UsdPhysics.FixedJoint):
            targets = root_prim.GetRelationship("physics:body0").GetTargets()
            if len(targets) != 1:
                report.issues.append(
                    ValidationIssue(
                        "error",
                        "INVALID_FIXED_ROOT",
                        "Fixed articulation root must reference exactly one root body through physics:body0",
                        report.articulation_root_path,
                    )
                )
            else:
                root_body_path = str(targets[0])
            if root_prim.GetAttribute("physics:jointEnabled").Get() is not True:
                report.issues.append(
                    ValidationIssue(
                        "error",
                        "ROOT_DISABLED",
                        "Fixed articulation root joint must be enabled",
                        report.articulation_root_path,
                    )
                )
        elif root_prim.HasAPI(UsdPhysics.RigidBodyAPI):
            root_body_path = report.articulation_root_path
            if config.require_fixed_base:
                report.issues.append(
                    ValidationIssue(
                        "error",
                        "FLOATING_ROOT",
                        "Profile requires a fixed-base articulation root joint",
                        report.articulation_root_path,
                    )
                )
        else:
            report.issues.append(
                ValidationIssue(
                    "error",
                    "UNSUPPORTED_ROOT",
                    "Articulation root must be a PhysicsFixedJoint or a rigid body",
                    report.articulation_root_path,
                )
            )
    report.root_body_path = root_body_path

    selected_prims: dict[str, Any] = {}
    for definition in config.joints:
        matches: dict[str, Any] = {}
        for path in definition.candidate_paths:
            prim = stage.GetPrimAtPath(path)
            if prim.IsValid() and prim.IsA(UsdPhysics.RevoluteJoint):
                matches[str(prim.GetPath())] = prim
        candidate_names = set(definition.candidate_names)
        for prim in prims:
            if prim.GetName() in candidate_names and prim.IsA(UsdPhysics.RevoluteJoint):
                matches[str(prim.GetPath())] = prim
        if not matches:
            report.issues.append(
                ValidationIssue(
                    "error",
                    "MISSING_JOINT",
                    f"Cannot resolve logical joint {definition.logical_name!r}; candidates={definition.candidate_names}",
                )
            )
            continue
        if len(matches) > 1:
            report.issues.append(
                ValidationIssue(
                    "error",
                    "AMBIGUOUS_JOINT",
                    f"Logical joint {definition.logical_name!r} matched {sorted(matches)}",
                )
            )
            continue
        path, prim = next(iter(matches.items()))
        selected_prims[definition.logical_name] = prim
        report.joint_paths[definition.logical_name] = path
        report.dof_names[definition.logical_name] = prim.GetName()

        if prim.GetAttribute("physics:jointEnabled").Get() is not True:
            report.issues.append(
                ValidationIssue("error", "JOINT_DISABLED", "RevoluteJoint must be enabled", path)
            )
        if "PhysicsDriveAPI:angular" in prim.GetAppliedSchemas():
            report.issues.append(
                ValidationIssue(
                    "error",
                    "DRIVE_CONFLICT",
                    "Angular Drive conflicts with direct-position articulation control",
                    path,
                )
            )
        body0 = prim.GetRelationship("physics:body0").GetTargets()
        body1 = prim.GetRelationship("physics:body1").GetTargets()
        if len(body0) != 1 or len(body1) != 1:
            report.issues.append(
                ValidationIssue(
                    "error",
                    "INVALID_BODY_RELATION",
                    "RevoluteJoint must reference exactly one body0 and one body1",
                    path,
                )
            )
        lower = prim.GetAttribute("physics:lowerLimit").Get()
        upper = prim.GetAttribute("physics:upperLimit").Get()
        try:
            lower_value = float(lower)
            upper_value = float(upper)
        except (TypeError, ValueError):
            report.issues.append(
                ValidationIssue("error", "MISSING_LIMIT", "Joint limits are missing", path)
            )
            continue
        safe_lower = lower_value + definition.safety_margin_degrees
        safe_upper = upper_value - definition.safety_margin_degrees
        if not all(math.isfinite(value) for value in (lower_value, upper_value)):
            report.issues.append(
                ValidationIssue("error", "NONFINITE_LIMIT", "Joint limits must be finite", path)
            )
        elif safe_lower >= safe_upper:
            report.issues.append(
                ValidationIssue(
                    "error",
                    "INVALID_SAFE_RANGE",
                    "Safety margin leaves no valid joint range",
                    path,
                )
            )
        else:
            report.limits_degrees[definition.logical_name] = (safe_lower, safe_upper)

    if len(selected_prims) == len(config.joints) and root_body_path:
        expected_parent = root_body_path
        ordered_bodies = [root_body_path]
        for definition in config.joints:
            prim = selected_prims[definition.logical_name]
            body0 = prim.GetRelationship("physics:body0").GetTargets()
            body1 = prim.GetRelationship("physics:body1").GetTargets()
            if len(body0) != 1 or len(body1) != 1:
                continue
            actual_parent = str(body0[0])
            child = str(body1[0])
            if actual_parent != expected_parent:
                report.issues.append(
                    ValidationIssue(
                        "error",
                        "BROKEN_CHAIN",
                        f"Expected body0={expected_parent}, got {actual_parent}",
                        str(prim.GetPath()),
                    )
                )
            if child in ordered_bodies:
                report.issues.append(
                    ValidationIssue(
                        "error",
                        "CHAIN_CYCLE",
                        f"Body {child} appears more than once in the articulation chain",
                        str(prim.GetPath()),
                    )
                )
            ordered_bodies.append(child)
            expected_parent = child
        report.body_paths = tuple(ordered_bodies)

    for body_path in report.body_paths:
        prim = stage.GetPrimAtPath(body_path)
        if not prim.IsValid():
            report.issues.append(
                ValidationIssue("error", "MISSING_BODY", "Referenced rigid body does not exist", body_path)
            )
            continue
        if not prim.HasAPI(UsdPhysics.RigidBodyAPI):
            report.issues.append(
                ValidationIssue("error", "MISSING_RIGID_BODY_API", "Body lacks RigidBodyAPI", body_path)
            )
        if not prim.HasAPI(UsdPhysics.MassAPI):
            report.issues.append(
                ValidationIssue("error", "MISSING_MASS_API", "Body lacks MassAPI", body_path)
            )
        if prim.GetAttribute("physics:rigidBodyEnabled").Get() is not True:
            report.issues.append(
                ValidationIssue("error", "BODY_DISABLED", "Rigid body must be enabled", body_path)
            )
        if prim.GetAttribute("physics:kinematicEnabled").Get() is not False:
            report.issues.append(
                ValidationIssue(
                    "error", "KINEMATIC_BODY", "Articulation link must be non-kinematic", body_path
                )
            )
        mass = prim.GetAttribute("physics:mass").Get()
        try:
            mass_value = float(mass)
        except (TypeError, ValueError):
            mass_value = math.nan
        if not math.isfinite(mass_value) or mass_value <= 0:
            report.issues.append(
                ValidationIssue("error", "INVALID_MASS", "Body mass must be positive", body_path)
            )
        inertia = prim.GetAttribute("physics:diagonalInertia").Get()
        try:
            inertia_values = tuple(float(inertia[index]) for index in range(3))
        except (TypeError, ValueError, IndexError):
            inertia_values = ()
        if len(inertia_values) != 3 or any(
            not math.isfinite(value) or value <= 0 for value in inertia_values
        ):
            report.issues.append(
                ValidationIssue(
                    "error", "INVALID_INERTIA", "Body diagonal inertia must be positive", body_path
                )
            )

    return report
