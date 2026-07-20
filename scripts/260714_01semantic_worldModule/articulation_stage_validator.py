"""Read-only USD contract checks for direct articulation position control.

The report and issue types intentionally have no Isaac Sim dependency.  ``pxr``
is imported only when :func:`validate_articulation_stage` is called, which keeps
report handling and unit tests usable from a normal Python interpreter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from joint_control_profile import JointControlProfile


@dataclass(frozen=True)
class ArticulationStageIssue:
    """One validation diagnostic produced without modifying the stage."""

    severity: str
    code: str
    message: str
    prim_path: str | None = None

    def __post_init__(self) -> None:
        if self.severity not in {"error", "warning", "info"}:
            raise ValueError(f"Invalid articulation issue severity: {self.severity!r}")
        if not self.code:
            raise ValueError("Articulation issue code cannot be empty")

    def format(self) -> str:
        location = f" [{self.prim_path}]" if self.prim_path else ""
        return f"{self.severity.upper()} {self.code}{location}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "prim_path": self.prim_path,
        }


@dataclass
class ArticulationStageReport:
    """Discovered articulation binding plus all static contract diagnostics."""

    articulation_root_path: str | None = None
    root_body_path: str | None = None
    joint_paths: dict[str, str] = field(default_factory=dict)
    dof_names: dict[str, str] = field(default_factory=dict)
    body_paths: tuple[str, ...] = ()
    limits_degrees: dict[str, tuple[float, float]] = field(default_factory=dict)
    issues: list[ArticulationStageIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ArticulationStageIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[ArticulationStageIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(
        self,
        severity: str,
        code: str,
        message: str,
        prim_path: str | None = None,
    ) -> None:
        self.issues.append(ArticulationStageIssue(severity, code, message, prim_path))

    def require_valid(self) -> "ArticulationStageReport":
        """Return this report, or raise with every blocking diagnostic."""

        if self.errors:
            details = "\n".join(issue.format() for issue in self.errors)
            raise RuntimeError(
                "Stage is not compatible with direct articulation control:\n" + details
            )
        return self

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe record suitable for the capture manifest."""

        return {
            "passed": self.ok,
            "articulation_root_path": self.articulation_root_path,
            "root_body_path": self.root_body_path,
            "joint_paths": dict(self.joint_paths),
            "dof_names": dict(self.dof_names),
            "body_paths": list(self.body_paths),
            "limits_degrees": {
                name: [float(bounds[0]), float(bounds[1])]
                for name, bounds in self.limits_degrees.items()
            },
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _usd_physics() -> Any:
    from pxr import UsdPhysics

    return UsdPhysics


def _valid_prims(stage: Any) -> list[Any]:
    return [prim for prim in stage.Traverse() if prim and prim.IsValid()]


def _targets(prim: Any, relationship_name: str) -> tuple[str, ...]:
    try:
        relationship = prim.GetRelationship(relationship_name)
        if not relationship or not relationship.IsValid():
            return ()
        return tuple(str(path) for path in relationship.GetTargets())
    except Exception:
        return ()


def _attribute(prim: Any, attribute_name: str) -> Any:
    try:
        attribute = prim.GetAttribute(attribute_name)
        if not attribute or not attribute.IsValid():
            return None
        return attribute.Get()
    except Exception:
        return None


def _has_angular_drive(prim: Any) -> bool:
    try:
        schemas = (str(schema) for schema in prim.GetAppliedSchemas())
        return any(schema == "PhysicsDriveAPI:angular" for schema in schemas)
    except Exception:
        # If schema inspection itself is broken, individual drive attributes are
        # not a reliable substitute.  The caller emits a dedicated error.
        raise


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result


def _vector3(value: Any) -> tuple[float, float, float] | None:
    try:
        result = tuple(float(value[index]) for index in range(3))
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if len(result) != 3:
        return None
    return result  # type: ignore[return-value]


def _definitions(profile: "JointControlProfile") -> tuple[Any, ...]:
    try:
        return tuple(profile.joints)
    except (AttributeError, TypeError):
        return ()


def _candidate_values(definition: Any, name: str) -> tuple[str, ...]:
    try:
        values: Iterable[Any] = getattr(definition, name)
        return tuple(str(value) for value in values if str(value))
    except (AttributeError, TypeError):
        return ()


def validate_articulation_stage(
    stage: Any,
    profile: "JointControlProfile",
) -> ArticulationStageReport:
    """Validate a fixed-base, four-link-chain excavator articulation.

    The function only reads USD state.  It never authors an API schema, changes
    an attribute, or advances the simulation timeline.
    """

    report = ArticulationStageReport()
    if stage is None:
        report.add("error", "NO_STAGE", "No USD stage is open")
        return report

    UsdPhysics = _usd_physics()
    prims = _valid_prims(stage)
    definitions = _definitions(profile)
    if len(definitions) != 4:
        report.add(
            "error",
            "PROFILE_JOINT_COUNT",
            f"Direct excavator control requires exactly 4 joint definitions, got {len(definitions)}",
        )

    root_candidates = [
        prim for prim in prims if prim.HasAPI(UsdPhysics.ArticulationRootAPI)
    ]
    root_prim = None
    root_hint = str(getattr(profile, "articulation_root_path", "") or "")
    if root_hint:
        candidate = stage.GetPrimAtPath(root_hint)
        if not candidate or not candidate.IsValid() or not candidate.HasAPI(
            UsdPhysics.ArticulationRootAPI
        ):
            report.add(
                "error",
                "INVALID_ROOT_HINT",
                "Configured path is missing PhysicsArticulationRootAPI",
                root_hint,
            )
        else:
            root_prim = candidate
    elif len(root_candidates) == 1:
        root_prim = root_candidates[0]
    elif not root_candidates:
        report.add("error", "MISSING_ROOT", "No PhysicsArticulationRootAPI was found")
    else:
        report.add(
            "error",
            "AMBIGUOUS_ROOT",
            f"Found {len(root_candidates)} articulation roots; configure articulation_root_path",
        )

    root_body_path: str | None = None
    require_fixed_base = bool(getattr(profile, "require_fixed_base", True))
    if root_prim is not None:
        root_path = str(root_prim.GetPath())
        report.articulation_root_path = root_path
        if root_prim.IsA(UsdPhysics.FixedJoint):
            root_targets = _targets(root_prim, "physics:body0")
            if len(root_targets) != 1:
                report.add(
                    "error",
                    "INVALID_FIXED_ROOT",
                    "Fixed articulation root must reference exactly one root body through physics:body0",
                    root_path,
                )
            else:
                root_body_path = root_targets[0]
            if _attribute(root_prim, "physics:jointEnabled") is not True:
                report.add(
                    "error",
                    "ROOT_DISABLED",
                    "Fixed articulation root joint must be enabled",
                    root_path,
                )
        elif root_prim.HasAPI(UsdPhysics.RigidBodyAPI):
            root_body_path = root_path
            if require_fixed_base:
                report.add(
                    "error",
                    "FLOATING_ROOT",
                    "Profile requires a fixed-base articulation root joint",
                    root_path,
                )
        else:
            report.add(
                "error",
                "UNSUPPORTED_ROOT",
                "Articulation root must be a PhysicsFixedJoint or a rigid body",
                root_path,
            )
    report.root_body_path = root_body_path

    selected_prims: dict[str, Any] = {}
    for definition in definitions:
        logical_name = str(getattr(definition, "logical_name", "") or "")
        if not logical_name:
            report.add("error", "INVALID_JOINT_DEFINITION", "Joint logical_name is empty")
            continue

        matches: dict[str, Any] = {}
        for candidate_path in _candidate_values(definition, "candidate_paths"):
            prim = stage.GetPrimAtPath(candidate_path)
            if prim and prim.IsValid() and prim.IsA(UsdPhysics.RevoluteJoint):
                matches[str(prim.GetPath())] = prim
        candidate_names = set(_candidate_values(definition, "candidate_names"))
        for prim in prims:
            if prim.GetName() in candidate_names and prim.IsA(UsdPhysics.RevoluteJoint):
                matches[str(prim.GetPath())] = prim

        if not matches:
            report.add(
                "error",
                "MISSING_JOINT",
                f"Cannot resolve logical joint {logical_name!r}",
            )
            continue
        if len(matches) > 1:
            report.add(
                "error",
                "AMBIGUOUS_JOINT",
                f"Logical joint {logical_name!r} matched {sorted(matches)}",
            )
            continue

        path, prim = next(iter(matches.items()))
        selected_prims[logical_name] = prim
        report.joint_paths[logical_name] = path
        report.dof_names[logical_name] = str(prim.GetName())

        if _attribute(prim, "physics:jointEnabled") is not True:
            report.add("error", "JOINT_DISABLED", "RevoluteJoint must be enabled", path)
        try:
            if _has_angular_drive(prim):
                report.add(
                    "error",
                    "DRIVE_CONFLICT",
                    "Angular Drive conflicts with direct-position articulation control",
                    path,
                )
        except Exception as exc:
            report.add(
                "error",
                "DRIVE_INSPECTION_FAILED",
                f"Could not inspect applied schemas: {exc}",
                path,
            )

        body0 = _targets(prim, "physics:body0")
        body1 = _targets(prim, "physics:body1")
        if len(body0) != 1 or len(body1) != 1:
            report.add(
                "error",
                "INVALID_BODY_RELATION",
                "RevoluteJoint must reference exactly one body0 and one body1",
                path,
            )

        lower = _float(_attribute(prim, "physics:lowerLimit"))
        upper = _float(_attribute(prim, "physics:upperLimit"))
        if lower is None or upper is None:
            report.add("error", "MISSING_LIMIT", "Joint limits are missing", path)
            continue
        if not math.isfinite(lower) or not math.isfinite(upper):
            report.add("error", "NONFINITE_LIMIT", "Joint limits must be finite", path)
            continue
        margin = _float(getattr(definition, "safety_margin_degrees", None))
        if margin is None or not math.isfinite(margin) or margin < 0:
            report.add(
                "error",
                "INVALID_SAFETY_MARGIN",
                f"Safety margin must be finite and non-negative, got {margin!r}",
                path,
            )
            continue
        safe_lower = lower + margin
        safe_upper = upper - margin
        if safe_lower >= safe_upper:
            report.add(
                "error",
                "INVALID_SAFE_RANGE",
                "Safety margin leaves no valid joint range",
                path,
            )
        else:
            report.limits_degrees[logical_name] = (safe_lower, safe_upper)

    # Resolve the complete root -> child chain in configured logical order.
    if len(selected_prims) == len(definitions) == 4 and root_body_path:
        expected_parent = root_body_path
        ordered_bodies = [root_body_path]
        for definition in definitions:
            logical_name = str(getattr(definition, "logical_name", "") or "")
            prim = selected_prims[logical_name]
            path = str(prim.GetPath())
            body0 = _targets(prim, "physics:body0")
            body1 = _targets(prim, "physics:body1")
            if len(body0) != 1 or len(body1) != 1:
                continue
            actual_parent = body0[0]
            child = body1[0]
            if actual_parent != expected_parent:
                report.add(
                    "error",
                    "BROKEN_CHAIN",
                    f"Expected body0={expected_parent}, got {actual_parent}",
                    path,
                )
            if child in ordered_bodies:
                report.add(
                    "error",
                    "CHAIN_CYCLE",
                    f"Body {child} appears more than once in the articulation chain",
                    path,
                )
            ordered_bodies.append(child)
            expected_parent = child
        report.body_paths = tuple(ordered_bodies)

    if report.body_paths and len(report.body_paths) != 5:
        report.add(
            "error",
            "INVALID_LINK_COUNT",
            f"Expected 5 rigid links in the four-joint chain, got {len(report.body_paths)}",
        )

    for body_path in report.body_paths:
        prim = stage.GetPrimAtPath(body_path)
        if not prim or not prim.IsValid():
            report.add("error", "MISSING_BODY", "Referenced rigid body does not exist", body_path)
            continue
        if not prim.HasAPI(UsdPhysics.RigidBodyAPI):
            report.add("error", "MISSING_RIGID_BODY_API", "Body lacks RigidBodyAPI", body_path)
        if not prim.HasAPI(UsdPhysics.MassAPI):
            report.add("error", "MISSING_MASS_API", "Body lacks MassAPI", body_path)
        if _attribute(prim, "physics:rigidBodyEnabled") is not True:
            report.add("error", "BODY_DISABLED", "Rigid body must be enabled", body_path)
        if _attribute(prim, "physics:kinematicEnabled") is not False:
            report.add(
                "error",
                "KINEMATIC_BODY",
                "Articulation link must be explicitly non-kinematic",
                body_path,
            )

        mass = _float(_attribute(prim, "physics:mass"))
        if mass is None or not math.isfinite(mass) or mass <= 0:
            report.add("error", "INVALID_MASS", "Body mass must be positive", body_path)

        inertia = _vector3(_attribute(prim, "physics:diagonalInertia"))
        if inertia is None or any(not math.isfinite(value) or value <= 0 for value in inertia):
            report.add(
                "error",
                "INVALID_INERTIA",
                "Body diagonal inertia must contain three positive finite values",
                body_path,
            )

    return report


__all__ = [
    "ArticulationStageIssue",
    "ArticulationStageReport",
    "validate_articulation_stage",
]
