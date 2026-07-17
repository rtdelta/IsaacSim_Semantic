"""USD Drive binding and safe target control for the excavator joints."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from trajectory import JOINT_NAMES, JointTrajectory, normalized_targets


@dataclass(frozen=True)
class JointSpec:
    name: str
    path: str


@dataclass
class BoundJoint:
    spec: JointSpec
    target_attribute: Any
    lower_limit: float
    upper_limit: float
    safe_lower: float
    safe_upper: float
    home_target: float


JOINT_SPECS = (
    JointSpec("cab", "/World/Joints/track_operator_cab_joint"),
    JointSpec("boom", "/World/Joints/platform_boom_joint"),
    JointSpec("small_arm", "/World/Joints/boom_small_arm_joint"),
    JointSpec("bucket", "/World/Joints/small_arm_bucket_joint"),
)


class ExcavatorJointController:
    """Resolve the four revolute joints and write angular Drive targets in degrees."""

    def __init__(self, safety_margin_degrees: float = 2.0) -> None:
        self.safety_margin_degrees = float(safety_margin_degrees)
        self.stage: Any | None = None
        self.joints: dict[str, BoundJoint] = {}

    @property
    def bound(self) -> bool:
        return self.stage is not None and len(self.joints) == len(JOINT_SPECS)

    def bind(self, stage: Any) -> None:
        if stage is None:
            raise RuntimeError("No USD stage is currently open")
        joints: dict[str, BoundJoint] = {}
        for spec in JOINT_SPECS:
            prim = stage.GetPrimAtPath(spec.path)
            if not prim.IsValid() or prim.GetTypeName() != "PhysicsRevoluteJoint":
                raise RuntimeError(f"Missing PhysicsRevoluteJoint: {spec.path}")
            lower_attr = prim.GetAttribute("physics:lowerLimit")
            upper_attr = prim.GetAttribute("physics:upperLimit")
            target_attr = prim.GetAttribute("drive:angular:physics:targetPosition")
            if not lower_attr.IsValid() or not upper_attr.IsValid() or not target_attr.IsValid():
                raise RuntimeError(f"Joint limits or angular Drive are missing: {spec.path}")
            lower = float(lower_attr.Get())
            upper = float(upper_attr.Get())
            home = float(target_attr.Get())
            safe_lower = lower + self.safety_margin_degrees
            safe_upper = upper - self.safety_margin_degrees
            if not safe_lower < safe_upper:
                raise RuntimeError(f"Safety margin leaves no valid range for joint: {spec.path}")
            joints[spec.name] = BoundJoint(
                spec=spec,
                target_attribute=target_attr,
                lower_limit=lower,
                upper_limit=upper,
                safe_lower=safe_lower,
                safe_upper=safe_upper,
                home_target=home,
            )
        self.stage = stage
        self.joints = joints

    def limits(self) -> dict[str, tuple[float, float]]:
        self._require_bound()
        return {
            name: (joint.safe_lower, joint.safe_upper)
            for name, joint in self.joints.items()
        }

    def read_targets(self) -> dict[str, float]:
        self._require_bound()
        return {
            name: float(joint.target_attribute.Get())
            for name, joint in self.joints.items()
        }

    def validate_targets(self, targets: Mapping[str, float]) -> dict[str, float]:
        self._require_bound()
        values = normalized_targets(targets)
        for name, value in values.items():
            joint = self.joints[name]
            if not math.isfinite(value) or not joint.safe_lower <= value <= joint.safe_upper:
                raise ValueError(
                    f"{name}={value:.6f} is outside safe range "
                    f"[{joint.safe_lower:.6f}, {joint.safe_upper:.6f}] degrees"
                )
        return values

    def set_targets(self, targets: Mapping[str, float]) -> dict[str, float]:
        values = self.validate_targets(targets)
        for name in JOINT_NAMES:
            if not self.joints[name].target_attribute.Set(values[name]):
                raise RuntimeError(f"Failed to set Drive target for joint: {name}")
        return values

    def reset_home(self) -> dict[str, float]:
        self._require_bound()
        home = {name: joint.home_target for name, joint in self.joints.items()}
        return self.set_targets(home)

    def validate_trajectory(self, trajectory: JointTrajectory) -> None:
        for index, frame in enumerate(trajectory.keyframes):
            try:
                self.validate_targets(frame.targets)
            except ValueError as exc:
                raise ValueError(
                    f"Trajectory sample {index} at t={frame.time:.9f}s is invalid: {exc}"
                ) from exc

    def describe(self) -> list[dict[str, float | str]]:
        self._require_bound()
        return [
            {
                "name": name,
                "path": joint.spec.path,
                "lower_limit": joint.lower_limit,
                "upper_limit": joint.upper_limit,
                "safe_lower": joint.safe_lower,
                "safe_upper": joint.safe_upper,
                "home_target": joint.home_target,
            }
            for name, joint in self.joints.items()
        ]

    def _require_bound(self) -> None:
        if not self.bound:
            raise RuntimeError("Excavator joints are not bound to a USD stage")

