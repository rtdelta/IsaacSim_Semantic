"""Optional deterministic CSV articulation playback plugin."""

from __future__ import annotations

import bisect
import csv
import math
from pathlib import Path
from typing import Any

from .config import MotionConfig
from .errors import ConfigurationError


class CsvArticulationMotion:
    """Drive named articulation DOFs from a time-indexed CSV trajectory.

    Settings schema:
    ``articulation_prim_path``, ``time_column``, ``joint_columns`` (DOF name to
    CSV column), optional ``angle_units`` (radians/degrees), ``interpolation``
    (linear/hold), and optional ``root_pose`` column mappings.
    """

    # Every CSV sample reconstructs the complete driven pose.  Workers may use
    # this capability to start a segment at an arbitrary dataset time instead
    # of replaying all earlier physics steps.
    supports_absolute_seek = True

    def __init__(self, config: MotionConfig, stage: Any) -> None:
        if not config.trajectory:
            raise ConfigurationError("CsvArticulationMotion requires scene.motion.trajectory")
        self.config = config
        self.stage = stage
        self.settings = config.settings
        self.prim_path = str(self.settings.get("articulation_prim_path", ""))
        self.time_column = str(self.settings.get("time_column", "time"))
        self.joint_columns = self.settings.get("joint_columns", {})
        self.interpolation = str(self.settings.get("interpolation", "linear"))
        self.angle_units = str(self.settings.get("angle_units", "radians"))
        self.root_pose = self.settings.get("root_pose")
        if not self.prim_path.startswith("/") or not isinstance(self.joint_columns, dict) or not self.joint_columns:
            raise ConfigurationError(
                "CsvArticulationMotion requires articulation_prim_path and joint_columns"
            )
        if self.interpolation not in {"linear", "hold"}:
            raise ConfigurationError("motion interpolation must be linear or hold")
        if self.angle_units not in {"radians", "degrees"}:
            raise ConfigurationError("motion angle_units must be radians or degrees")
        self.rows = self._load(Path(config.trajectory))
        self.times = [row[self.time_column] for row in self.rows]
        self.articulation = None
        self.joint_indices: list[int] = []

    def _load(self, path: Path) -> list[dict[str, float]]:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                raw_rows = list(csv.DictReader(stream))
        except FileNotFoundError as exc:
            raise ConfigurationError(f"Motion trajectory does not exist: {path}") from exc
        required = {self.time_column, *map(str, self.joint_columns.values())}
        if self.root_pose:
            required.update(self.root_pose.get("position", []))
            required.update(self.root_pose.get("orientation_wxyz", []))
        rows: list[dict[str, float]] = []
        for index, raw in enumerate(raw_rows, 2):
            missing = required - set(raw)
            if missing:
                raise ConfigurationError(
                    f"Trajectory is missing columns at line {index}: {sorted(missing)}"
                )
            try:
                rows.append({key: float(raw[key]) for key in required})
            except (TypeError, ValueError) as exc:
                raise ConfigurationError(f"Invalid trajectory number at line {index}") from exc
        if not rows or any(
            rows[index][self.time_column] <= rows[index - 1][self.time_column]
            for index in range(1, len(rows))
        ):
            raise ConfigurationError("Trajectory times must be non-empty and strictly increasing")
        return rows

    def initialize(self) -> None:
        from isaacsim.core.prims import SingleArticulation

        self.articulation = SingleArticulation(prim_path=self.prim_path)
        self.articulation.initialize()
        self.joint_indices = [
            int(self.articulation.get_dof_index(dof_name))
            for dof_name in self.joint_columns
        ]
        if any(index < 0 for index in self.joint_indices):
            raise RuntimeError(f"Could not resolve every configured DOF at {self.prim_path}")

    def _values(self, dataset_time: float) -> dict[str, float]:
        right = bisect.bisect_right(self.times, dataset_time)
        if right <= 0:
            return self.rows[0]
        if right >= len(self.rows):
            return self.rows[-1]
        left_row, right_row = self.rows[right - 1], self.rows[right]
        if self.interpolation == "hold":
            return left_row
        left_time, right_time = left_row[self.time_column], right_row[self.time_column]
        alpha = (dataset_time - left_time) / (right_time - left_time)
        return {
            key: left_row[key] + (right_row[key] - left_row[key]) * alpha
            for key in left_row
        }

    def before_step(self, dataset_time: float) -> None:
        if self.articulation is None:
            raise RuntimeError("Motion driver is not initialized")
        import numpy as np

        row = self._values(dataset_time)
        factor = math.pi / 180.0 if self.angle_units == "degrees" else 1.0
        positions = np.asarray(
            [row[column] * factor for column in self.joint_columns.values()], dtype=float
        )
        self.articulation.set_joint_positions(
            positions, joint_indices=np.asarray(self.joint_indices, dtype=int)
        )
        if self.root_pose:
            position = np.asarray([row[key] for key in self.root_pose["position"]], dtype=float)
            orientation = np.asarray(
                [row[key] for key in self.root_pose["orientation_wxyz"]], dtype=float
            )
            orientation /= np.linalg.norm(orientation)
            self.articulation.set_world_pose(position=position, orientation=orientation)

    def seek(self, dataset_time: float) -> None:
        """Apply the absolute CSV pose for a random-access segment start."""

        self.before_step(dataset_time)

    def after_step(self, dataset_time: float) -> None:
        _ = dataset_time

    def close(self) -> None:
        self.articulation = None
