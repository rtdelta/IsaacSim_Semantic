"""Optional deterministic motion sources."""

import bisect
import csv
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from semantic_world_v04.core.models import MotionSpec
from semantic_world_v04.project.paths import ProjectPathResolver


class NoMotionController:
    supports_absolute_seek = True
    requires_physics = False

    def initialize(self) -> None:
        return

    def apply(self, dataset_time: float) -> None:
        _ = dataset_time

    def seek(self, dataset_time: float) -> None:
        _ = dataset_time

    def close(self) -> None:
        return


class CsvTrajectory:
    """Strict, interpolated numeric CSV independent of Isaac Sim."""

    def __init__(
        self,
        path: Path,
        *,
        time_column: str,
        required_columns: List[str],
        interpolation: str = "linear",
    ) -> None:
        if interpolation not in {"linear", "hold"}:
            raise ValueError("CSV interpolation must be linear or hold")
        self.path = Path(path)
        self.time_column = time_column
        self.required_columns = list(dict.fromkeys(required_columns))
        self.interpolation = interpolation
        self.rows = self._load()
        self.times = [row[self.time_column] for row in self.rows]

    def _load(self) -> List[Dict[str, float]]:
        with self.path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise ValueError(f"trajectory has no CSV header: {self.path}")
            required = {self.time_column, *self.required_columns}
            missing = required - set(reader.fieldnames)
            if missing:
                raise ValueError(
                    f"trajectory is missing columns: {', '.join(sorted(missing))}"
                )
            rows: List[Dict[str, float]] = []
            for line_number, raw in enumerate(reader, 2):
                try:
                    rows.append(
                        {key: float(raw[key]) for key in required}
                    )
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"invalid trajectory number at line {line_number}"
                    ) from exc
        if not rows:
            raise ValueError("trajectory must contain at least one sample")
        if any(
            rows[index][self.time_column]
            <= rows[index - 1][self.time_column]
            for index in range(1, len(rows))
        ):
            raise ValueError("trajectory times must be strictly increasing")
        return rows

    def sample(self, dataset_time: float) -> Dict[str, float]:
        right = bisect.bisect_right(self.times, dataset_time)
        if right <= 0:
            return dict(self.rows[0])
        if right >= len(self.rows):
            return dict(self.rows[-1])
        left_row = self.rows[right - 1]
        right_row = self.rows[right]
        if self.interpolation == "hold":
            return dict(left_row)
        left_time = left_row[self.time_column]
        right_time = right_row[self.time_column]
        alpha = (dataset_time - left_time) / (right_time - left_time)
        return {
            key: left_row[key] + (right_row[key] - left_row[key]) * alpha
            for key in left_row
        }


class CsvArticulationMotion:
    """Drive named articulation DOFs and an optional root pose from CSV."""

    def __init__(
        self,
        spec: MotionSpec,
        *,
        project_dir: Optional[Path] = None,
    ) -> None:
        if not spec.source_path:
            raise ValueError("csv_articulation motion requires source_path")
        self.spec = spec
        self.supports_absolute_seek = bool(spec.supports_absolute_seek)
        self.requires_physics = True
        options = spec.options
        self.prim_path = str(options.get("articulation_prim_path", ""))
        self.time_column = str(options.get("time_column", "time"))
        self.joint_columns = options.get("joint_columns", {})
        self.interpolation = str(options.get("interpolation", "linear"))
        self.angle_units = str(options.get("angle_units", "radians"))
        self.root_pose = options.get("root_pose")
        if not self.prim_path.startswith("/"):
            raise ValueError("articulation_prim_path must be an absolute Prim path")
        if not isinstance(self.joint_columns, dict) or not self.joint_columns:
            raise ValueError("joint_columns must map DOF names to CSV columns")
        if self.angle_units not in {"radians", "degrees"}:
            raise ValueError("angle_units must be radians or degrees")
        source_path = spec.source_path
        if project_dir is not None:
            source_path = ProjectPathResolver.resolve(source_path, project_dir)
        required = [str(value) for value in self.joint_columns.values()]
        if self.root_pose:
            required.extend(str(value) for value in self.root_pose.get("position", []))
            required.extend(
                str(value)
                for value in self.root_pose.get("orientation_wxyz", [])
            )
        self.trajectory = CsvTrajectory(
            Path(str(source_path)),
            time_column=self.time_column,
            required_columns=required,
            interpolation=self.interpolation,
        )
        self.articulation = None
        self.joint_indices = None

    def initialize(self) -> None:
        from isaacsim.core.prims import SingleArticulation  # type: ignore
        import numpy as np

        self.articulation = SingleArticulation(prim_path=self.prim_path)
        self.articulation.initialize()
        self.joint_indices = np.asarray(
            [
                int(self.articulation.get_dof_index(dof_name))
                for dof_name in self.joint_columns
            ],
            dtype=int,
        )
        if any(index < 0 for index in self.joint_indices):
            raise RuntimeError(
                f"could not resolve every configured DOF at {self.prim_path}"
            )

    def apply(self, dataset_time: float) -> None:
        if self.articulation is None or self.joint_indices is None:
            raise RuntimeError("CSV articulation motion is not initialized")
        import numpy as np

        row = self.trajectory.sample(dataset_time)
        factor = math.pi / 180.0 if self.angle_units == "degrees" else 1.0
        positions = np.asarray(
            [
                row[str(column)] * factor
                for column in self.joint_columns.values()
            ],
            dtype=float,
        )
        self.articulation.set_joint_positions(
            positions, joint_indices=self.joint_indices
        )
        if self.root_pose:
            position = np.asarray(
                [row[str(key)] for key in self.root_pose["position"]],
                dtype=float,
            )
            orientation = np.asarray(
                [
                    row[str(key)]
                    for key in self.root_pose["orientation_wxyz"]
                ],
                dtype=float,
            )
            norm = float(np.linalg.norm(orientation))
            if norm <= 0:
                raise ValueError("trajectory root quaternion has zero norm")
            orientation /= norm
            self.articulation.set_world_pose(
                position=position, orientation=orientation
            )

    def seek(self, dataset_time: float) -> None:
        self.apply(dataset_time)

    def close(self) -> None:
        self.articulation = None
        self.joint_indices = None


def create_motion_controller(
    spec: MotionSpec, source_project_path: str
) -> Any:
    if spec.plugin == "none":
        return NoMotionController()
    if spec.plugin == "csv_articulation":
        project_dir = (
            Path(source_project_path)
            if source_project_path
            else None
        )
        return CsvArticulationMotion(spec, project_dir=project_dir)
    raise ValueError(f"unknown motion plugin: {spec.plugin}")
