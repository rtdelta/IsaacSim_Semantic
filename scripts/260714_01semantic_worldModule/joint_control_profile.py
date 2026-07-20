"""Validated, self-contained configuration for excavator articulation control.

This module intentionally has no Isaac Sim imports.  It can therefore be used by
command-line validation and unit tests before SimulationApp is started.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


JOINT_CONTROL_PROFILE_SCHEMA_VERSION = 1
EXPECTED_JOINT_COUNT = 4


class JointControlProfileError(ValueError):
    """Raised when a joint-control profile or trajectory sidecar is invalid."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise JointControlProfileError(f"{label} must be a non-empty string")
    return value.strip()


def _string_tuple(value: Any, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise JointControlProfileError(f"{label} must be a JSON array")
    result = tuple(_required_string(item, f"{label} item") for item in value)
    if not result and not allow_empty:
        raise JointControlProfileError(f"{label} must not be empty")
    if len(set(result)) != len(result):
        raise JointControlProfileError(f"{label} contains duplicate values")
    return result


@dataclass(frozen=True)
class JointControlDefinition:
    """Logical joint identity and safe motion settings independent of a USD."""

    logical_name: str
    candidate_names: tuple[str, ...]
    candidate_paths: tuple[str, ...]
    safety_margin_degrees: float

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], index: int) -> "JointControlDefinition":
        if not isinstance(raw, Mapping):
            raise JointControlProfileError(f"joints[{index}] must be a JSON object")
        logical_name = _required_string(raw.get("logical_name"), f"joints[{index}].logical_name")
        candidate_names = _string_tuple(
            raw.get("candidate_names", []),
            f"joint {logical_name!r} candidate_names",
            allow_empty=True,
        )
        candidate_paths = _string_tuple(
            raw.get("candidate_paths", []),
            f"joint {logical_name!r} candidate_paths",
            allow_empty=True,
        )
        if not candidate_names and not candidate_paths:
            raise JointControlProfileError(
                f"Joint {logical_name!r} needs candidate_names or candidate_paths"
            )
        if any(not path.startswith("/") for path in candidate_paths):
            raise JointControlProfileError(
                f"Joint {logical_name!r} candidate_paths must be absolute USD paths"
            )
        try:
            margin = float(raw.get("safety_margin_degrees"))
        except (TypeError, ValueError) as exc:
            raise JointControlProfileError(
                f"Joint {logical_name!r} safety_margin_degrees must be numeric"
            ) from exc
        if not math.isfinite(margin) or margin < 0:
            raise JointControlProfileError(
                f"Joint {logical_name!r} safety_margin_degrees must be finite and non-negative"
            )
        return cls(
            logical_name=logical_name,
            candidate_names=candidate_names,
            candidate_paths=candidate_paths,
            safety_margin_degrees=margin,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "logical_name": self.logical_name,
            "candidate_names": list(self.candidate_names),
            "candidate_paths": list(self.candidate_paths),
            "safety_margin_degrees": self.safety_margin_degrees,
        }


@dataclass(frozen=True)
class TrajectoryMetadataContract:
    """Compatibility expectations for an optional Recorder metadata sidecar."""

    sidecar_suffix: str
    angle_unit: str
    compatible_control_modes: tuple[str, ...]
    require_profile_match: bool

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "TrajectoryMetadataContract":
        if not isinstance(raw, Mapping):
            raise JointControlProfileError("trajectory_metadata must be a JSON object")
        suffix = _required_string(
            raw.get("sidecar_suffix", ".metadata.json"),
            "trajectory_metadata.sidecar_suffix",
        )
        if "/" in suffix or "\\" in suffix:
            raise JointControlProfileError(
                "trajectory_metadata.sidecar_suffix must not contain path separators"
            )
        angle_unit = _required_string(
            raw.get("angle_unit", "degree"), "trajectory_metadata.angle_unit"
        )
        modes = _string_tuple(
            raw.get("compatible_control_modes", ["articulation_direct_position"]),
            "trajectory_metadata.compatible_control_modes",
        )
        require_profile_match = raw.get("require_profile_match", True)
        if not isinstance(require_profile_match, bool):
            raise JointControlProfileError(
                "trajectory_metadata.require_profile_match must be boolean"
            )
        return cls(
            sidecar_suffix=suffix,
            angle_unit=angle_unit,
            compatible_control_modes=modes,
            require_profile_match=require_profile_match,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sidecar_suffix": self.sidecar_suffix,
            "angle_unit": self.angle_unit,
            "compatible_control_modes": list(self.compatible_control_modes),
            "require_profile_match": self.require_profile_match,
        }


@dataclass(frozen=True)
class JointControlProfile:
    """Four-joint articulation contract loaded from a versioned JSON file."""

    schema_version: int
    source_path: Path
    source_sha256: str
    profile_name: str
    articulation_root_path: str | None
    require_fixed_base: bool
    forbid_angular_drives: bool
    readback_tolerance_degrees: float
    joints: tuple[JointControlDefinition, ...]
    trajectory_metadata: TrajectoryMetadataContract

    @property
    def logical_joint_names(self) -> tuple[str, ...]:
        return tuple(joint.logical_name for joint in self.joints)

    @classmethod
    def load(cls, path: str | Path) -> "JointControlProfile":
        source_path = Path(path).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"Joint-control profile not found: {source_path}")
        try:
            with source_path.open("r", encoding="utf-8") as stream:
                raw = json.load(stream)
        except json.JSONDecodeError as exc:
            raise JointControlProfileError(
                f"Cannot parse joint-control profile: {source_path}"
            ) from exc
        if not isinstance(raw, dict):
            raise JointControlProfileError("Joint-control profile root must be a JSON object")

        try:
            schema_version = int(raw.get("schema_version", 0))
        except (TypeError, ValueError) as exc:
            raise JointControlProfileError("schema_version must be an integer") from exc
        if schema_version != JOINT_CONTROL_PROFILE_SCHEMA_VERSION:
            raise JointControlProfileError(
                f"Unsupported joint-control profile schema version: {schema_version}"
            )
        profile_name = _required_string(raw.get("profile_name"), "profile_name")

        root_value = raw.get("articulation_root_path")
        if root_value is None:
            articulation_root_path = None
        else:
            articulation_root_path = _required_string(
                root_value, "articulation_root_path"
            )
            if not articulation_root_path.startswith("/"):
                raise JointControlProfileError(
                    "articulation_root_path must be an absolute USD path or null"
                )

        require_fixed_base = raw.get("require_fixed_base", True)
        forbid_angular_drives = raw.get("forbid_angular_drives", True)
        if not isinstance(require_fixed_base, bool):
            raise JointControlProfileError("require_fixed_base must be boolean")
        if not isinstance(forbid_angular_drives, bool):
            raise JointControlProfileError("forbid_angular_drives must be boolean")
        try:
            readback_tolerance_degrees = float(raw.get("readback_tolerance_degrees", 0.05))
        except (TypeError, ValueError) as exc:
            raise JointControlProfileError(
                "readback_tolerance_degrees must be numeric"
            ) from exc
        if (
            not math.isfinite(readback_tolerance_degrees)
            or readback_tolerance_degrees <= 0
        ):
            raise JointControlProfileError(
                "readback_tolerance_degrees must be positive and finite"
            )

        joints_raw = raw.get("joints")
        if not isinstance(joints_raw, list):
            raise JointControlProfileError("joints must be a JSON array")
        if len(joints_raw) != EXPECTED_JOINT_COUNT:
            raise JointControlProfileError(
                f"A four-joint control profile requires exactly 4 joints, got {len(joints_raw)}"
            )
        joints = tuple(
            JointControlDefinition.from_dict(item, index)
            for index, item in enumerate(joints_raw)
        )
        logical_names = tuple(joint.logical_name for joint in joints)
        if len(set(logical_names)) != EXPECTED_JOINT_COUNT:
            raise JointControlProfileError(
                f"Logical joint names must be unique, got {logical_names}"
            )

        candidate_paths = [path for joint in joints for path in joint.candidate_paths]
        if len(set(candidate_paths)) != len(candidate_paths):
            raise JointControlProfileError("candidate_paths must not be shared by logical joints")
        candidate_names = [name for joint in joints for name in joint.candidate_names]
        if len(set(candidate_names)) != len(candidate_names):
            raise JointControlProfileError("candidate_names must not be shared by logical joints")

        metadata = TrajectoryMetadataContract.from_dict(raw.get("trajectory_metadata", {}))
        return cls(
            schema_version=schema_version,
            source_path=source_path,
            source_sha256=_sha256_file(source_path),
            profile_name=profile_name,
            articulation_root_path=articulation_root_path,
            require_fixed_base=require_fixed_base,
            forbid_angular_drives=forbid_angular_drives,
            readback_tolerance_degrees=readback_tolerance_degrees,
            joints=joints,
            trajectory_metadata=metadata,
        )

    def trajectory_metadata_path(self, csv_path: str | Path) -> Path:
        """Return the Recorder sidecar path associated with a trajectory CSV."""

        trajectory_path = Path(csv_path).expanduser().resolve()
        return trajectory_path.with_name(
            f"{trajectory_path.stem}{self.trajectory_metadata.sidecar_suffix}"
        )

    def load_and_validate_trajectory_metadata(
        self,
        csv_path: str | Path,
        metadata_path: str | Path | None = None,
        required: bool = False,
    ) -> dict[str, Any] | None:
        """Load a Recorder sidecar when present and validate trajectory compatibility.

        Missing metadata is accepted by default so hand-authored CSV trajectories remain
        usable.  A sidecar that does exist is never silently ignored when malformed.
        """

        resolved = (
            Path(metadata_path).expanduser().resolve()
            if metadata_path is not None
            else self.trajectory_metadata_path(csv_path)
        )
        if not resolved.is_file():
            if required:
                raise FileNotFoundError(f"Trajectory metadata sidecar not found: {resolved}")
            return None
        try:
            with resolved.open("r", encoding="utf-8") as stream:
                metadata = json.load(stream)
        except json.JSONDecodeError as exc:
            raise JointControlProfileError(
                f"Cannot parse trajectory metadata sidecar: {resolved}"
            ) from exc
        if not isinstance(metadata, dict):
            raise JointControlProfileError("Trajectory metadata root must be a JSON object")
        self._validate_trajectory_metadata(metadata)
        return metadata

    def _validate_trajectory_metadata(self, metadata: Mapping[str, Any]) -> None:
        if metadata.get("completed") is not True:
            raise JointControlProfileError("Trajectory metadata completed must be true")
        joint_order = metadata.get("joint_order")
        if joint_order != list(self.logical_joint_names):
            raise JointControlProfileError(
                "Trajectory metadata joint_order must exactly match profile order "
                f"{list(self.logical_joint_names)}, got {joint_order!r}"
            )
        expected_unit = self.trajectory_metadata.angle_unit
        if metadata.get("angle_unit") != expected_unit:
            raise JointControlProfileError(
                f"Trajectory metadata angle_unit must be {expected_unit!r}"
            )

        control_mode = metadata.get("control_mode")
        if "control_mode" in metadata and (
            control_mode not in self.trajectory_metadata.compatible_control_modes
        ):
            raise JointControlProfileError(
                f"Trajectory metadata control_mode {control_mode!r} is incompatible; "
                f"expected one of {self.trajectory_metadata.compatible_control_modes}"
            )
        recorded_profile = metadata.get("profile")
        if (
            self.trajectory_metadata.require_profile_match
            and "profile" in metadata
            and recorded_profile != self.profile_name
        ):
            raise JointControlProfileError(
                f"Trajectory metadata profile {recorded_profile!r} does not match "
                f"{self.profile_name!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_path": str(self.source_path),
            "sha256": self.source_sha256,
            "profile_name": self.profile_name,
            "articulation_root_path": self.articulation_root_path,
            "require_fixed_base": self.require_fixed_base,
            "forbid_angular_drives": self.forbid_angular_drives,
            "readback_tolerance_degrees": self.readback_tolerance_degrees,
            "joints": [joint.to_dict() for joint in self.joints],
            "logical_joint_names": list(self.logical_joint_names),
            "trajectory_metadata": self.trajectory_metadata.to_dict(),
        }
