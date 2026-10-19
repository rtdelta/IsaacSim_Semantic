"""Replay the Fangshan excavator CSV from Isaac Sim's Script Editor.

Intended workflow:

1. Open ``combine_scene_05.usda`` in the Isaac Sim 6.0.1 GUI.
2. Open Window > Script Editor.
3. Open or paste this file and press Run.

The script is deliberately self-contained.  It drives the four articulation
DOFs and the floating articulation root directly from the recorded absolute
state.  Re-running the script stops the previous player before installing a
new one.
"""

from __future__ import annotations

import asyncio
import builtins
import csv
import json
import math
import os
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import numpy as np


# ---------------------------------------------------------------------------
# User configuration
# ---------------------------------------------------------------------------

EXPECTED_STAGE_PATH = Path(
    "/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_05.usda"
)
CSV_PATH = Path(
    "/root/gpufree-data/semantic/scripts/trajectories/trajectory_0813_01.csv"
)
ARTICULATION_ROOT_PATH = "/Excavator_Fangshan_03/track_prim"

# (logical CSV column, Isaac Sim DOF name, joint Prim path)
JOINT_BINDINGS = (
    (
        "cab",
        "track_operator_cab_joint",
        "/Excavator_Fangshan_03/Joints/track_operator_cab_joint",
    ),
    (
        "boom",
        "platform_boom_joint",
        "/Excavator_Fangshan_03/Joints/platform_boom_joint",
    ),
    (
        "small_arm",
        "boom_small_arm_joint",
        "/Excavator_Fangshan_03/Joints/boom_small_arm_joint",
    ),
    (
        "bucket",
        "small_arm_bucket_joint",
        "/Excavator_Fangshan_03/Joints/small_arm_bucket_joint",
    ),
)

# hold: keep authoritatively applying the last frame after the CSV ends.
# once: apply the last frame once and leave the player in FINISHED state.
# loop: only accepted for a trajectory whose first and last complete pose match.
PLAYBACK_MODE = "hold"
PLAYBACK_SPEED = 1.0
AUTO_PLAY_TIMELINE = True
REQUIRE_EXPECTED_STAGE = True
REQUIRE_METADATA = True
MAX_INITIALIZATION_UPDATES = 600
PROGRESS_LOG_INTERVAL_SECONDS = 60.0


TIME_COLUMN = "time"
ROOT_POSITION_COLUMNS = (
    "root_world_x_m",
    "root_world_y_m",
    "root_world_z_m",
)
ROOT_QUATERNION_COLUMNS = (
    "root_quat_w",
    "root_quat_x",
    "root_quat_y",
    "root_quat_z",
)
PLAYER_BUILTINS_KEY = "_fangshan_excavator_csv_player"
SCRIPT_VERSION = "1.0.0"


class PlaybackError(RuntimeError):
    """Raised when the trajectory or current Isaac Sim Stage is incompatible."""


@dataclass(frozen=True)
class TrajectorySample:
    time: float
    joints_degrees: np.ndarray
    root_position_meters: np.ndarray
    root_orientation_wxyz: np.ndarray


class ExcavatorTrajectory:
    """Validated in-memory representation of the recorded absolute state."""

    def __init__(
        self,
        path: Path,
        times: np.ndarray,
        joints_degrees: np.ndarray,
        root_positions_meters: np.ndarray,
        root_orientations_wxyz: np.ndarray,
    ) -> None:
        self.path = path
        self.times = times
        self.joints_degrees = joints_degrees
        self.root_positions_meters = root_positions_meters
        self.root_orientations_wxyz = root_orientations_wxyz
        self.duration = float(times[-1])

    @classmethod
    def from_csv(cls, path: str | Path) -> "ExcavatorTrajectory":
        source = Path(path).expanduser().resolve()
        if not source.is_file():
            raise PlaybackError(f"Trajectory CSV does not exist: {source}")

        joint_columns = tuple(item[0] for item in JOINT_BINDINGS)
        selected_columns = (
            TIME_COLUMN,
            *joint_columns,
            *ROOT_POSITION_COLUMNS,
            *ROOT_QUATERNION_COLUMNS,
        )
        rows: list[list[float]] = []
        with source.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fieldnames = tuple(reader.fieldnames or ())
            missing = [name for name in selected_columns if name not in fieldnames]
            if missing:
                raise PlaybackError(
                    f"Trajectory is missing required columns {missing}; got {fieldnames}"
                )
            for line_number, row in enumerate(reader, start=2):
                try:
                    values = [float(row[name]) for name in selected_columns]
                except (TypeError, ValueError) as exc:
                    raise PlaybackError(
                        f"Invalid numeric value in trajectory line {line_number}"
                    ) from exc
                if not all(math.isfinite(value) for value in values):
                    raise PlaybackError(
                        f"Non-finite numeric value in trajectory line {line_number}"
                    )
                rows.append(values)

        if len(rows) < 2:
            raise PlaybackError("Trajectory must contain at least two data rows")
        matrix = np.asarray(rows, dtype=np.float64)
        times = matrix[:, 0]
        if not math.isclose(float(times[0]), 0.0, abs_tol=1.0e-9):
            raise PlaybackError(
                f"First trajectory time must be 0.0, got {float(times[0])}"
            )
        if np.any(np.diff(times) <= 0.0):
            raise PlaybackError("Trajectory times must be strictly increasing")

        joint_end = 1 + len(joint_columns)
        position_end = joint_end + len(ROOT_POSITION_COLUMNS)
        joints = matrix[:, 1:joint_end]
        positions = matrix[:, joint_end:position_end]
        quaternions = matrix[:, position_end : position_end + 4]
        norms = np.linalg.norm(quaternions, axis=1)
        if np.any(norms <= 1.0e-12):
            bad_index = int(np.flatnonzero(norms <= 1.0e-12)[0])
            raise PlaybackError(
                f"Trajectory contains a zero root quaternion at data row {bad_index}"
            )
        quaternions = quaternions / norms[:, None]

        return cls(source, times, joints, positions, quaternions)

    @property
    def sample_count(self) -> int:
        return int(self.times.size)

    def validate_loop_closure(self) -> None:
        joint_error = float(
            np.max(np.abs(self.joints_degrees[-1] - self.joints_degrees[0]))
        )
        position_error = float(
            np.linalg.norm(
                self.root_positions_meters[-1] - self.root_positions_meters[0]
            )
        )
        dot = abs(
            float(
                np.dot(
                    self.root_orientations_wxyz[-1],
                    self.root_orientations_wxyz[0],
                )
            )
        )
        orientation_error = math.degrees(
            2.0 * math.acos(max(-1.0, min(1.0, dot)))
        )
        if joint_error > 1.0e-4 or position_error > 1.0e-5 or orientation_error > 1.0e-3:
            raise PlaybackError(
                "loop mode requires a closed complete pose; "
                f"joint_error_deg={joint_error:.6g}, "
                f"position_error_m={position_error:.6g}, "
                f"orientation_error_deg={orientation_error:.6g}"
            )

    def discontinuity_summary(self) -> dict[str, Any]:
        joint_deltas = np.abs(np.diff(self.joints_degrees, axis=0))
        position_deltas = np.linalg.norm(
            np.diff(self.root_positions_meters, axis=0), axis=1
        )
        dots = np.abs(
            np.sum(
                self.root_orientations_wxyz[:-1]
                * self.root_orientations_wxyz[1:],
                axis=1,
            )
        )
        angle_deltas = np.degrees(2.0 * np.arccos(np.clip(dots, -1.0, 1.0)))
        combined = np.maximum.reduce(
            (
                np.max(joint_deltas, axis=1) / 10.0,
                position_deltas,
                angle_deltas / 10.0,
            )
        )
        worst = int(np.argmax(combined))
        return {
            "time": float(self.times[worst + 1]),
            "joint_step_degrees": {
                binding[0]: float(joint_deltas[worst, index])
                for index, binding in enumerate(JOINT_BINDINGS)
            },
            "root_position_step_meters": float(position_deltas[worst]),
            "root_orientation_step_degrees": float(angle_deltas[worst]),
        }

    def sample(self, trajectory_time: float) -> TrajectorySample:
        value = max(0.0, min(float(trajectory_time), self.duration))
        if value <= 0.0:
            return self._sample_at_index(0, value)
        if value >= self.duration:
            return self._sample_at_index(-1, value)

        right = int(np.searchsorted(self.times, value, side="right"))
        left = right - 1
        left_time = float(self.times[left])
        right_time = float(self.times[right])
        alpha = (value - left_time) / (right_time - left_time)
        joints = self.joints_degrees[left] + alpha * (
            self.joints_degrees[right] - self.joints_degrees[left]
        )
        position = self.root_positions_meters[left] + alpha * (
            self.root_positions_meters[right] - self.root_positions_meters[left]
        )
        orientation = _slerp_wxyz(
            self.root_orientations_wxyz[left],
            self.root_orientations_wxyz[right],
            alpha,
        )
        return TrajectorySample(value, joints, position, orientation)

    def _sample_at_index(self, index: int, value: float) -> TrajectorySample:
        return TrajectorySample(
            value,
            self.joints_degrees[index].copy(),
            self.root_positions_meters[index].copy(),
            self.root_orientations_wxyz[index].copy(),
        )


def _slerp_wxyz(left: np.ndarray, right: np.ndarray, alpha: float) -> np.ndarray:
    q0 = np.asarray(left, dtype=np.float64)
    q1 = np.asarray(right, dtype=np.float64)
    dot = float(np.dot(q0, q1))
    if dot < 0.0:
        q1 = -q1
        dot = -dot
    dot = max(-1.0, min(1.0, dot))
    if dot > 0.9995:
        result = q0 + float(alpha) * (q1 - q0)
        return result / np.linalg.norm(result)
    theta_0 = math.acos(dot)
    sin_theta_0 = math.sin(theta_0)
    theta = theta_0 * float(alpha)
    scale0 = math.sin(theta_0 - theta) / sin_theta_0
    scale1 = math.sin(theta) / sin_theta_0
    result = scale0 * q0 + scale1 * q1
    return result / np.linalg.norm(result)


def _read_and_validate_metadata(trajectory: ExcavatorTrajectory) -> dict[str, Any]:
    metadata_path = trajectory.path.with_name(
        f"{trajectory.path.stem}.metadata.json"
    )
    if not metadata_path.is_file():
        if REQUIRE_METADATA:
            raise PlaybackError(f"Trajectory metadata does not exist: {metadata_path}")
        return {}
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlaybackError(f"Cannot read trajectory metadata: {metadata_path}") from exc

    expected_dofs = {logical: dof for logical, dof, _ in JOINT_BINDINGS}
    checks = (
        (
            metadata.get("angle_unit") == "degree",
            "metadata angle_unit must be 'degree'",
        ),
        (
            metadata.get("root_quaternion_order") == "wxyz",
            "metadata root_quaternion_order must be 'wxyz'",
        ),
        (
            metadata.get("root_motion_enabled") is True,
            "metadata must enable root motion",
        ),
        (
            metadata.get("articulation_root") == ARTICULATION_ROOT_PATH,
            "metadata articulation_root does not match the configured root",
        ),
        (
            metadata.get("dof_names") == expected_dofs,
            "metadata DOF names do not match the configured bindings",
        ),
        (
            int(metadata.get("sample_count", -1)) == trajectory.sample_count,
            "metadata sample_count does not match the CSV",
        ),
    )
    failures = [message for condition, message in checks if not condition]
    if failures:
        raise PlaybackError("; ".join(failures))
    return metadata


def _identifier_to_path(identifier: str) -> str:
    value = str(identifier or "")
    if value.startswith("file:"):
        value = unquote(urlparse(value).path)
    return os.path.realpath(os.path.expanduser(value)) if value else ""


def _validate_current_stage() -> Any:
    import omni.usd
    from pxr import UsdGeom, UsdPhysics

    stage = omni.usd.get_context().get_stage()
    if stage is None:
        raise PlaybackError("No USD Stage is currently open")

    root_layer = stage.GetRootLayer()
    stage_identifier = root_layer.realPath or root_layer.identifier
    actual_stage_path = _identifier_to_path(stage_identifier)
    expected_stage_path = os.path.realpath(str(EXPECTED_STAGE_PATH))
    if REQUIRE_EXPECTED_STAGE and actual_stage_path != expected_stage_path:
        raise PlaybackError(
            "Open the expected Stage before running this script: "
            f"expected={expected_stage_path}, actual={actual_stage_path or stage_identifier}"
        )

    meters_per_unit = float(UsdGeom.GetStageMetersPerUnit(stage))
    if not math.isclose(meters_per_unit, 1.0, rel_tol=0.0, abs_tol=1.0e-9):
        raise PlaybackError(
            f"Stage metersPerUnit must be 1.0 for this CSV, got {meters_per_unit}"
        )

    root = stage.GetPrimAtPath(ARTICULATION_ROOT_PATH)
    if not root.IsValid():
        raise PlaybackError(
            f"Articulation root Prim is missing: {ARTICULATION_ROOT_PATH}"
        )
    if not root.HasAPI(UsdPhysics.ArticulationRootAPI):
        raise PlaybackError(
            f"Prim is missing PhysicsArticulationRootAPI: {ARTICULATION_ROOT_PATH}"
        )
    if not root.HasAPI(UsdPhysics.RigidBodyAPI):
        raise PlaybackError(
            f"Articulation root is not a rigid body: {ARTICULATION_ROOT_PATH}"
        )
    kinematic = UsdPhysics.RigidBodyAPI(root).GetKinematicEnabledAttr().Get()
    if bool(kinematic):
        raise PlaybackError("Articulation root must be floating, not kinematic")

    missing_joints = [
        path for _, _, path in JOINT_BINDINGS if not stage.GetPrimAtPath(path).IsValid()
    ]
    if missing_joints:
        raise PlaybackError(f"Stage is missing configured joint Prims: {missing_joints}")
    return stage


class ExcavatorCsvPlayer:
    """Own the Isaac articulation, physics subscription, and playback clock."""

    def __init__(self) -> None:
        self.state = "CREATED"
        self.trajectory: ExcavatorTrajectory | None = None
        self.metadata: dict[str, Any] = {}
        self.articulation: Any | None = None
        self.dof_indices: tuple[int, ...] = ()
        self.physics_subscription: Any | None = None
        self.startup_task: asyncio.Task[Any] | None = None
        self.timeline: Any | None = None
        self.elapsed_seconds = 0.0
        self.last_trajectory_time = 0.0
        self.next_progress_log_time = PROGRESS_LOG_INTERVAL_SECONDS
        self.callback_kind = ""
        self._fault_printed = False

    def prepare(self) -> None:
        if PLAYBACK_MODE not in {"hold", "once", "loop"}:
            raise PlaybackError("PLAYBACK_MODE must be hold, once, or loop")
        if not math.isfinite(PLAYBACK_SPEED) or PLAYBACK_SPEED <= 0.0:
            raise PlaybackError("PLAYBACK_SPEED must be a positive finite number")

        self.state = "LOADING"
        self.trajectory = ExcavatorTrajectory.from_csv(CSV_PATH)
        self.metadata = _read_and_validate_metadata(self.trajectory)
        if PLAYBACK_MODE == "loop":
            self.trajectory.validate_loop_closure()
        _validate_current_stage()

        from isaacsim.core.experimental.prims import Articulation

        self.articulation = Articulation(ARTICULATION_ROOT_PATH)
        expected_names = tuple(binding[1] for binding in JOINT_BINDINGS)
        available_names = tuple(self.articulation.dof_names)
        missing = [name for name in expected_names if name not in available_names]
        if missing:
            raise PlaybackError(
                f"Articulation is missing DOFs {missing}; available={available_names}"
            )
        indices = self.articulation.get_dof_indices(list(expected_names)).numpy()
        self.dof_indices = tuple(int(value) for value in indices.reshape(-1).tolist())

        import omni.physx
        import omni.timeline

        physx = omni.physx.get_physx_interface()
        subscribe_post_step = getattr(physx, "subscribe_physics_on_step_events", None)
        if callable(subscribe_post_step):
            self.physics_subscription = subscribe_post_step(
                self._on_physics_step,
                False,  # authoritative pose after physics, before rendering
                0,
            )
            self.callback_kind = "physics_post_step"
        else:
            self.physics_subscription = physx.subscribe_physics_step_events(
                self._on_physics_step
            )
            self.callback_kind = "physics_step"

        self.timeline = omni.timeline.get_timeline_interface()
        self.state = "WAITING_FOR_PHYSICS"
        if AUTO_PLAY_TIMELINE and not self.timeline.is_playing():
            self.timeline.play()
            commit = getattr(self.timeline, "commit", None)
            if callable(commit):
                commit()

        summary = self.trajectory.discontinuity_summary()
        print(
            "[excavator-csv] Loaded "
            f"{self.trajectory.sample_count} samples, "
            f"duration={self.trajectory.duration:.6f}s, "
            f"mode={PLAYBACK_MODE}, speed={PLAYBACK_SPEED}x"
        )
        print(
            "[excavator-csv] Largest recorded step is preserved: "
            f"t={summary['time']:.6f}s, "
            f"joints_deg={summary['joint_step_degrees']}, "
            f"root_m={summary['root_position_step_meters']:.6f}, "
            f"root_deg={summary['root_orientation_step_degrees']:.6f}"
        )
        self.startup_task = asyncio.ensure_future(self._wait_until_ready())

    async def _wait_until_ready(self) -> None:
        import omni.kit.app

        app = omni.kit.app.get_app()
        try:
            for _ in range(MAX_INITIALIZATION_UPDATES):
                if self.state != "WAITING_FOR_PHYSICS":
                    return
                if self._articulation_ready():
                    self._apply_sample(self.trajectory.sample(0.0))
                    self.state = "RUNNING"
                    print(
                        "[excavator-csv] RUNNING: "
                        f"root={ARTICULATION_ROOT_PATH}, "
                        f"dof_indices={self.dof_indices}, "
                        f"callback={self.callback_kind}"
                    )
                    print(
                        "[excavator-csv] Stop with: "
                        "import builtins; "
                        f"builtins.{PLAYER_BUILTINS_KEY}.stop('manual')"
                    )
                    return
                await app.next_update_async()
            raise PlaybackError(
                "Articulation physics tensor did not become ready; "
                "confirm the Timeline is playing and the payload is loaded"
            )
        except asyncio.CancelledError:
            return
        except BaseException as exc:
            self._record_fault(exc)

    def _articulation_ready(self) -> bool:
        if self.articulation is None:
            return False
        try:
            return bool(self.articulation.is_physics_tensor_entity_valid())
        except Exception:
            return False

    def _on_physics_step(self, dt: float) -> None:
        if self.state != "RUNNING" or self.trajectory is None:
            return
        try:
            step = max(0.0, float(dt)) * float(PLAYBACK_SPEED)
            next_elapsed = self.elapsed_seconds + step
            if PLAYBACK_MODE == "loop":
                trajectory_time = next_elapsed % self.trajectory.duration
            else:
                trajectory_time = min(next_elapsed, self.trajectory.duration)

            self._apply_sample(self.trajectory.sample(trajectory_time))
            self.elapsed_seconds = next_elapsed
            self.last_trajectory_time = trajectory_time

            if next_elapsed >= self.next_progress_log_time:
                progress = 100.0 * trajectory_time / self.trajectory.duration
                print(
                    "[excavator-csv] "
                    f"time={trajectory_time:.3f}/{self.trajectory.duration:.3f}s "
                    f"({progress:.1f}%)"
                )
                self.next_progress_log_time += PROGRESS_LOG_INTERVAL_SECONDS

            if PLAYBACK_MODE == "once" and next_elapsed >= self.trajectory.duration:
                self.state = "FINISHED"
                print("[excavator-csv] FINISHED: final CSV pose applied")
            elif PLAYBACK_MODE == "hold" and next_elapsed >= self.trajectory.duration:
                if self.next_progress_log_time != math.inf:
                    print("[excavator-csv] HOLDING final CSV pose")
                    self.next_progress_log_time = math.inf
        except BaseException as exc:
            # Keep the subscription object alive but make subsequent callbacks no-ops.
            # Releasing a PhysX subscription from inside its callback is unsafe.
            self._record_fault(exc)

    def _apply_sample(self, sample: TrajectorySample) -> None:
        if self.articulation is None:
            raise PlaybackError("Articulation has not been created")
        if not self._articulation_ready():
            raise PlaybackError(
                "Articulation physics tensor became invalid; after Timeline Stop, "
                "run this script again"
            )
        joint_radians = np.radians(sample.joints_degrees).astype(np.float32)[None, :]
        joint_zeros = np.zeros_like(joint_radians)
        indices = list(self.dof_indices)
        self.articulation.set_dof_positions(
            joint_radians,
            dof_indices=indices,
        )
        self.articulation.set_dof_velocities(
            joint_zeros,
            dof_indices=indices,
        )

        position = np.asarray(sample.root_position_meters, dtype=np.float32)[None, :]
        orientation = np.asarray(sample.root_orientation_wxyz, dtype=np.float32)[
            None, :
        ]
        root_zeros = np.zeros((1, 3), dtype=np.float32)
        self.articulation.set_world_poses(
            positions=position,
            orientations=orientation,
        )
        self.articulation.set_velocities(
            linear_velocities=root_zeros,
            angular_velocities=root_zeros,
        )

    def _record_fault(self, exc: BaseException) -> None:
        self.state = "ERROR"
        if not self._fault_printed:
            self._fault_printed = True
            print(f"[excavator-csv] ERROR: {exc}")
            traceback.print_exc()

    def status(self) -> dict[str, Any]:
        duration = self.trajectory.duration if self.trajectory is not None else 0.0
        return {
            "version": SCRIPT_VERSION,
            "state": self.state,
            "csv": str(CSV_PATH),
            "stage": str(EXPECTED_STAGE_PATH),
            "articulation_root": ARTICULATION_ROOT_PATH,
            "playback_mode": PLAYBACK_MODE,
            "playback_speed": PLAYBACK_SPEED,
            "trajectory_time": self.last_trajectory_time,
            "duration": duration,
            "percent": (
                100.0 * self.last_trajectory_time / duration if duration > 0.0 else 0.0
            ),
            "callback": self.callback_kind,
        }

    def stop(self, reason: str = "manual") -> None:
        if self.startup_task is not None and not self.startup_task.done():
            self.startup_task.cancel()
        self.startup_task = None
        self.state = "STOPPED"
        # Dropping the Carbonite subscription outside its callback unsubscribes it.
        self.physics_subscription = None
        self.articulation = None
        self.dof_indices = ()
        print(f"[excavator-csv] STOPPED ({reason}); Timeline was left unchanged")


def install_and_start() -> ExcavatorCsvPlayer:
    previous = getattr(builtins, PLAYER_BUILTINS_KEY, None)
    if previous is not None and hasattr(previous, "stop"):
        try:
            previous.stop("replaced by a new Script Editor run")
        except Exception as exc:
            print(f"[excavator-csv] Warning: could not stop previous player: {exc}")

    player = ExcavatorCsvPlayer()
    setattr(builtins, PLAYER_BUILTINS_KEY, player)
    try:
        player.prepare()
    except BaseException as exc:
        player._record_fault(exc)
        player.physics_subscription = None
        raise
    return player


def stop_active_player() -> None:
    player = getattr(builtins, PLAYER_BUILTINS_KEY, None)
    if player is None:
        print("[excavator-csv] No active player")
        return
    player.stop("manual")


def print_active_player_status() -> None:
    player = getattr(builtins, PLAYER_BUILTINS_KEY, None)
    if player is None:
        print("[excavator-csv] No active player")
        return
    print(f"[excavator-csv] status={player.status()}")


if __name__ == "__main__":
    PLAYER = install_and_start()

