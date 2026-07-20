"""Configuration model for a generic four-joint excavator articulation."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigurationError(ValueError):
    """Raised when a project profile is incomplete or inconsistent."""


@dataclass(frozen=True)
class JointDefinition:
    """Logical joint identity and GUI defaults independent of a concrete USD path."""

    logical_name: str
    display_name: str
    candidate_names: tuple[str, ...]
    candidate_paths: tuple[str, ...] = ()
    default_speed_degrees: float = 5.0
    home_degrees: float = 0.0
    safety_margin_degrees: float = 2.0

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "JointDefinition":
        try:
            result = cls(
                logical_name=str(value["logical_name"]).strip(),
                display_name=str(value.get("display_name", value["logical_name"])).strip(),
                candidate_names=tuple(str(item).strip() for item in value["candidate_names"]),
                candidate_paths=tuple(str(item).strip() for item in value.get("candidate_paths", ())),
                default_speed_degrees=float(value.get("default_speed_degrees", 5.0)),
                home_degrees=float(value.get("home_degrees", 0.0)),
                safety_margin_degrees=float(value.get("safety_margin_degrees", 2.0)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError(f"Invalid joint definition: {value!r}") from exc
        result.validate()
        return result

    def validate(self) -> None:
        if not self.logical_name:
            raise ConfigurationError("Joint logical_name cannot be empty")
        if not self.display_name:
            raise ConfigurationError(f"Joint {self.logical_name!r} has an empty display_name")
        if not self.candidate_names and not self.candidate_paths:
            raise ConfigurationError(
                f"Joint {self.logical_name!r} needs candidate_names or candidate_paths"
            )
        if any(not item for item in (*self.candidate_names, *self.candidate_paths)):
            raise ConfigurationError(f"Joint {self.logical_name!r} contains an empty candidate")
        for field_name, number in (
            ("default_speed_degrees", self.default_speed_degrees),
            ("home_degrees", self.home_degrees),
            ("safety_margin_degrees", self.safety_margin_degrees),
        ):
            if not math.isfinite(number):
                raise ConfigurationError(
                    f"Joint {self.logical_name!r} has non-finite {field_name}"
                )
        if self.default_speed_degrees <= 0:
            raise ConfigurationError(
                f"Joint {self.logical_name!r} default speed must be positive"
            )
        if self.safety_margin_degrees < 0:
            raise ConfigurationError(
                f"Joint {self.logical_name!r} safety margin cannot be negative"
            )


@dataclass(frozen=True)
class ProjectConfig:
    """Validated project configuration loaded from a reusable JSON profile."""

    profile_name: str
    joints: tuple[JointDefinition, ...]
    articulation_root_path: str | None = None
    require_fixed_base: bool = True
    arrival_tolerance_degrees: float = 0.01
    max_update_dt: float = 0.05
    default_csv_directory: str = "trajectories"
    default_csv_filename: str = "excavator_actual_angles.csv"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ProjectConfig":
        try:
            root_path = value.get("articulation_root_path")
            result = cls(
                profile_name=str(value["profile_name"]).strip(),
                joints=tuple(JointDefinition.from_dict(item) for item in value["joints"]),
                articulation_root_path=str(root_path).strip() if root_path else None,
                require_fixed_base=bool(value.get("require_fixed_base", True)),
                arrival_tolerance_degrees=float(
                    value.get("arrival_tolerance_degrees", 0.01)
                ),
                max_update_dt=float(value.get("max_update_dt", 0.05)),
                default_csv_directory=str(
                    value.get("default_csv_directory", "trajectories")
                ).strip(),
                default_csv_filename=str(
                    value.get("default_csv_filename", "excavator_actual_angles.csv")
                ).strip(),
            )
        except ConfigurationError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError("Invalid project profile") from exc
        result.validate()
        return result

    @property
    def logical_joint_names(self) -> tuple[str, ...]:
        return tuple(joint.logical_name for joint in self.joints)

    def validate(self) -> None:
        if not self.profile_name:
            raise ConfigurationError("profile_name cannot be empty")
        if len(self.joints) != 4:
            raise ConfigurationError(
                f"A four-joint excavator profile requires 4 joints, got {len(self.joints)}"
            )
        logical_names = self.logical_joint_names
        if len(set(logical_names)) != len(logical_names):
            raise ConfigurationError(f"Duplicate logical joint names: {logical_names}")
        if not math.isfinite(self.arrival_tolerance_degrees) or self.arrival_tolerance_degrees <= 0:
            raise ConfigurationError("arrival_tolerance_degrees must be positive and finite")
        if not math.isfinite(self.max_update_dt) or self.max_update_dt <= 0:
            raise ConfigurationError("max_update_dt must be positive and finite")
        if not self.default_csv_directory:
            raise ConfigurationError("default_csv_directory cannot be empty")
        if Path(self.default_csv_filename).name != self.default_csv_filename:
            raise ConfigurationError("default_csv_filename must be a filename, not a path")
        if not self.default_csv_filename.lower().endswith(".csv"):
            raise ConfigurationError("default_csv_filename must end in .csv")

    def resolve_csv_directory(self, project_root: Path) -> Path:
        configured = Path(self.default_csv_directory).expanduser()
        if configured.is_absolute():
            return configured.resolve()
        return (project_root / configured).resolve()


def load_project_config(path: str | Path) -> ProjectConfig:
    """Load and validate a UTF-8 JSON profile."""

    profile_path = Path(path).expanduser().resolve()
    if not profile_path.is_file():
        raise FileNotFoundError(f"Profile not found: {profile_path}")
    try:
        value = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Cannot read profile: {profile_path}") from exc
    if not isinstance(value, dict):
        raise ConfigurationError("Profile root must be a JSON object")
    return ProjectConfig.from_dict(value)
