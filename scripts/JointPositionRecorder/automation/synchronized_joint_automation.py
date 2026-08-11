"""Independent synchronized Boom/Small arm/Bucket automation for Isaac Sim.

This module deliberately writes only three selected articulation DOFs.  Cab is
neither commanded nor removed from the existing four-joint recorder; the
recorder can therefore keep sampling Cab on every update even while its value
is unchanged.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


JOINT_ORDER = ("boom", "small_arm", "bucket")
MOVING_STATES = {"ALIGNING", "RUNNING"}


class AutomationConfigurationError(ValueError):
    """Raised when the independent automation JSON is invalid."""


@dataclass(frozen=True)
class JointBinding:
    logical_name: str
    dof_name: str
    joint_path: str


@dataclass(frozen=True)
class Waypoint:
    name: str
    angles_degrees: tuple[float, float, float]
    duration_from_previous_seconds: float | None


@dataclass(frozen=True)
class AutomationConfig:
    articulation_root_path: str
    interpolation: str
    position_tolerance_degrees: float
    joint_limit_margin_degrees: float
    initial_alignment_duration_seconds: float
    joints: tuple[JointBinding, ...]
    waypoints: tuple[Waypoint, ...]

    @property
    def cycle_duration_seconds(self) -> float:
        return sum(
            float(waypoint.duration_from_previous_seconds)
            for waypoint in self.waypoints[1:]
        )


def _finite_float(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise AutomationConfigurationError(f"{label} must be a number") from exc
    if not math.isfinite(result):
        raise AutomationConfigurationError(f"{label} must be finite")
    return result


def load_automation_config(path: str | Path) -> AutomationConfig:
    """Load and strictly validate the editable automation definition."""

    config_path = Path(path).expanduser().resolve()
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AutomationConfigurationError(f"Cannot read {config_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise AutomationConfigurationError("Configuration root must be a JSON object")

    root_path = str(raw.get("articulation_root_path", "")).strip()
    if not root_path.startswith("/"):
        raise AutomationConfigurationError("articulation_root_path must be an absolute prim path")

    interpolation = str(raw.get("interpolation", "smoothstep")).strip().lower()
    if interpolation not in {"linear", "smoothstep"}:
        raise AutomationConfigurationError("interpolation must be 'linear' or 'smoothstep'")

    tolerance = _finite_float(
        raw.get("position_tolerance_degrees", 0.1),
        "position_tolerance_degrees",
    )
    margin = _finite_float(
        raw.get("joint_limit_margin_degrees", 0.0),
        "joint_limit_margin_degrees",
    )
    alignment_duration = _finite_float(
        raw.get("initial_alignment_duration_seconds", 3.0),
        "initial_alignment_duration_seconds",
    )
    if tolerance <= 0:
        raise AutomationConfigurationError("position_tolerance_degrees must be positive")
    if margin < 0:
        raise AutomationConfigurationError("joint_limit_margin_degrees cannot be negative")
    if alignment_duration <= 0:
        raise AutomationConfigurationError(
            "initial_alignment_duration_seconds must be positive"
        )

    raw_joints = raw.get("joints")
    if not isinstance(raw_joints, dict) or set(raw_joints) != set(JOINT_ORDER):
        raise AutomationConfigurationError(
            f"joints must contain exactly {list(JOINT_ORDER)}; Cab must not be commanded"
        )
    joints: list[JointBinding] = []
    for logical_name in JOINT_ORDER:
        value = raw_joints[logical_name]
        if not isinstance(value, dict):
            raise AutomationConfigurationError(f"joints.{logical_name} must be an object")
        dof_name = str(value.get("dof_name", "")).strip()
        joint_path = str(value.get("joint_path", "")).strip()
        if not dof_name or not joint_path.startswith("/"):
            raise AutomationConfigurationError(
                f"joints.{logical_name} needs dof_name and an absolute joint_path"
            )
        joints.append(JointBinding(logical_name, dof_name, joint_path))
    if len({joint.dof_name for joint in joints}) != len(joints):
        raise AutomationConfigurationError("Automation DOF names must be unique")

    raw_waypoints = raw.get("waypoints")
    if not isinstance(raw_waypoints, list) or len(raw_waypoints) < 2:
        raise AutomationConfigurationError("waypoints must contain an anchor and at least one target")
    waypoints: list[Waypoint] = []
    names: set[str] = set()
    for index, value in enumerate(raw_waypoints):
        if not isinstance(value, dict):
            raise AutomationConfigurationError(f"waypoints[{index}] must be an object")
        name = str(value.get("name", "")).strip()
        if not name or name in names:
            raise AutomationConfigurationError(f"waypoints[{index}].name must be non-empty and unique")
        names.add(name)
        raw_angles = value.get("angles_degrees")
        if not isinstance(raw_angles, dict) or set(raw_angles) != set(JOINT_ORDER):
            raise AutomationConfigurationError(
                f"waypoints[{index}].angles_degrees must contain exactly {list(JOINT_ORDER)}"
            )
        angles = tuple(
            _finite_float(raw_angles[joint], f"waypoints[{index}].angles_degrees.{joint}")
            for joint in JOINT_ORDER
        )
        duration: float | None = None
        if index > 0:
            duration = _finite_float(
                value.get("duration_from_previous_seconds"),
                f"waypoints[{index}].duration_from_previous_seconds",
            )
            if duration <= 0:
                raise AutomationConfigurationError(
                    f"waypoints[{index}] duration must be positive"
                )
        waypoints.append(Waypoint(name, angles, duration))

    return AutomationConfig(
        articulation_root_path=root_path,
        interpolation=interpolation,
        position_tolerance_degrees=tolerance,
        joint_limit_margin_degrees=margin,
        initial_alignment_duration_seconds=alignment_duration,
        joints=tuple(joints),
        waypoints=tuple(waypoints),
    )


class SelectedDofAdapter:
    """Read/write only the three selected DOFs of a larger articulation."""

    def __init__(self, root_path: str, dof_names: Sequence[str]) -> None:
        self.root_path = str(root_path)
        self.dof_names = tuple(str(value) for value in dof_names)
        self._articulation = None
        self._indices: tuple[int, ...] = ()

    def bind(self) -> None:
        try:
            from isaacsim.core.experimental.prims import Articulation

            articulation = Articulation(self.root_path)
            available = tuple(articulation.dof_names)
            missing = [name for name in self.dof_names if name not in available]
            if missing:
                raise RuntimeError(f"Missing DOFs {missing}; available DOFs={list(available)}")
            values = articulation.get_dof_indices(list(self.dof_names)).numpy().reshape(-1)
            self._indices = tuple(int(value) for value in values.tolist())
            self._articulation = articulation
        except Exception as exc:
            raise RuntimeError(f"Cannot bind articulation {self.root_path}: {exc}") from exc

    @property
    def ready(self) -> bool:
        if self._articulation is None or not self._indices:
            return False
        try:
            return bool(self._articulation.is_physics_tensor_entity_valid())
        except Exception:
            return False

    def _require_ready(self) -> None:
        if not self.ready:
            raise RuntimeError(
                "Articulation physics tensor is not ready; play the Timeline and wait for a frame"
            )

    def get_positions_degrees(self) -> tuple[float, float, float]:
        self._require_ready()
        values = self._articulation.get_dof_positions(
            dof_indices=list(self._indices)
        ).numpy().reshape(-1)
        if values.size != len(self._indices):
            raise RuntimeError(f"Unexpected selected-DOF position shape: {values.shape}")
        return tuple(math.degrees(float(value)) for value in values.tolist())  # type: ignore[return-value]

    def set_positions_degrees(self, values_degrees: Sequence[float]) -> None:
        self._require_ready()
        values = tuple(float(value) for value in values_degrees)
        if len(values) != len(self._indices) or any(not math.isfinite(value) for value in values):
            raise RuntimeError(f"Expected {len(self._indices)} finite joint positions")
        import numpy as np

        radians = np.asarray(
            [[math.radians(value) for value in values]],
            dtype=np.float32,
        )
        zeros = np.zeros_like(radians)
        indices = list(self._indices)
        self._articulation.set_dof_positions(radians, dof_indices=indices)
        self._articulation.set_dof_velocities(zeros, dof_indices=indices)

    def clear_selected_velocities(self) -> None:
        if not self.ready:
            return
        import numpy as np

        zeros = np.zeros((1, len(self._indices)), dtype=np.float32)
        self._articulation.set_dof_velocities(zeros, dof_indices=list(self._indices))

    def shutdown(self) -> None:
        self._articulation = None
        self._indices = ()


class SynchronizedJointAutomationWindow:
    """Small independent panel that owns the synchronized three-DOF sequence."""

    def __init__(self, config_path: str | Path) -> None:
        import carb.eventdispatcher
        import omni.kit.app
        import omni.timeline
        import omni.ui as ui
        import omni.usd

        self.config_path = Path(config_path).expanduser().resolve()
        self.config = load_automation_config(self.config_path)
        self._ui = ui
        self._usd_context = omni.usd.get_context()
        self._timeline = omni.timeline.get_timeline_interface()
        self._stage = None
        self._adapter: SelectedDofAdapter | None = None
        self._runtime_ready = False
        self._closed = False
        self._state = "UNBOUND"
        self._paused_from_state: str | None = None
        self._segment_start = (0.0, 0.0, 0.0)
        self._segment_target = (0.0, 0.0, 0.0)
        self._segment_duration = 0.0
        self._segment_elapsed = 0.0
        self._target_waypoint_index = 0
        self._completed_cycles = 0
        self._limits_degrees: dict[str, tuple[float, float]] = {}
        self._build_window()
        self._update_subscription = carb.eventdispatcher.get_eventdispatcher().observe_event(
            event_name=omni.kit.app.GLOBAL_EVENT_UPDATE,
            on_event=self._on_update,
            observer_name="waji-synchronized-joint-automation-update",
        )
        self.bind_current_stage()

    def _build_window(self) -> None:
        ui = self._ui
        self._window = ui.Window(
            "Excavator Synchronized Joint Automation",
            width=760,
            height=430,
            visible=True,
        )
        self._window.set_visibility_changed_fn(self._on_visibility_changed)
        with self._window.frame:
            with ui.VStack(spacing=8, height=0):
                ui.Label("Boom + Small arm + Bucket synchronized automation", height=28)
                ui.Label(
                    "Cab is not commanded; the existing recorder still samples Cab every frame.",
                    height=24,
                )
                self._config_label = ui.Label(f"Config: {self.config_path}", height=40, word_wrap=True)
                self._cycle_label = ui.Label("", height=24)
                self._limits_label = ui.Label("Joint limits: waiting for stage", height=45, word_wrap=True)
                ui.Separator()
                with ui.HStack(height=36, spacing=7):
                    ui.Button("Bind stage", clicked_fn=self.bind_current_stage)
                    ui.Button("Start", clicked_fn=self.start)
                    ui.Button("Pause", clicked_fn=self.pause)
                    ui.Button("Resume", clicked_fn=self.resume)
                    ui.Button("Stop", clicked_fn=self.stop)
                    ui.Button("Reload JSON", clicked_fn=self.reload_config)
                self._motion_label = ui.Label("State: UNBOUND", height=70, word_wrap=True)
                self._angles_label = ui.Label("Current angles: --", height=28)
                self._status_label = ui.Label("Initializing...", height=60, word_wrap=True)
        self._refresh_config_label()

    def _refresh_config_label(self) -> None:
        segments = " + ".join(
            f"{float(item.duration_from_previous_seconds):g}s"
            for item in self.config.waypoints[1:]
        )
        self._cycle_label.text = (
            f"Cycle: {segments} = {self.config.cycle_duration_seconds:g}s | "
            f"interpolation={self.config.interpolation}"
        )

    def bind_current_stage(self) -> None:
        try:
            self._release_binding()
            stage = self._usd_context.get_stage()
            if stage is None:
                raise RuntimeError("No USD stage is open")
            root = stage.GetPrimAtPath(self.config.articulation_root_path)
            if not root.IsValid():
                raise RuntimeError(
                    f"Articulation root does not exist: {self.config.articulation_root_path}"
                )
            adapter = SelectedDofAdapter(
                self.config.articulation_root_path,
                [joint.dof_name for joint in self.config.joints],
            )
            adapter.bind()
            self._stage = stage
            self._adapter = adapter
            self._state = "WAITING"
            if not self._timeline.is_playing():
                self._timeline.play()
                self._timeline.commit()
            self._set_status("Stage bound; waiting for the Articulation physics tensor")
        except Exception as exc:
            self._set_error(exc)

    def _validate_stage_limits(self) -> None:
        from pxr import UsdPhysics

        assert self._stage is not None
        limits: dict[str, tuple[float, float]] = {}
        for joint in self.config.joints:
            prim = self._stage.GetPrimAtPath(joint.joint_path)
            if not prim.IsValid() or not prim.IsA(UsdPhysics.RevoluteJoint):
                raise RuntimeError(f"Revolute joint does not exist: {joint.joint_path}")
            schema = UsdPhysics.RevoluteJoint(prim)
            lower_raw = schema.GetLowerLimitAttr().Get()
            upper_raw = schema.GetUpperLimitAttr().Get()
            if lower_raw is None or upper_raw is None:
                raise RuntimeError(f"Joint limits are missing: {joint.joint_path}")
            lower = float(lower_raw) + self.config.joint_limit_margin_degrees
            upper = float(upper_raw) - self.config.joint_limit_margin_degrees
            if lower > upper:
                raise RuntimeError(f"Invalid safe joint limits for {joint.logical_name}")
            limits[joint.logical_name] = (lower, upper)

        for waypoint in self.config.waypoints:
            for index, logical_name in enumerate(JOINT_ORDER):
                angle = waypoint.angles_degrees[index]
                lower, upper = limits[logical_name]
                if not lower <= angle <= upper:
                    raise RuntimeError(
                        f"Waypoint {waypoint.name}: {logical_name}={angle:g} deg is outside "
                        f"the active Stage range [{lower:g}, {upper:g}] deg"
                    )
        self._limits_degrees = limits
        self._limits_label.text = "Joint limits: " + ", ".join(
            f"{name}=[{limits[name][0]:g}, {limits[name][1]:g}] deg"
            for name in JOINT_ORDER
        )

    def _manual_joint_motion_active(self) -> bool:
        """Detect the existing panel's active Move command without modifying it."""

        module = sys.modules.get("joint_position_recorder.gui")
        window = getattr(module, "_ACTIVE_WINDOW", None) if module is not None else None
        controller = getattr(window, "_controller", None) if window is not None else None
        state = getattr(controller, "state", None)
        return getattr(state, "value", str(state)) == "MOVING"

    def start(self) -> None:
        try:
            self._require_ready()
            if self._state in MOVING_STATES:
                raise RuntimeError("Automation is already running")
            if self._manual_joint_motion_active():
                raise RuntimeError(
                    "The existing panel is moving arm joints; press its Stop button first"
                )
            assert self._adapter is not None
            current = self._adapter.get_positions_degrees()
            home = self.config.waypoints[0].angles_degrees
            self._completed_cycles = 0
            if max(abs(a - b) for a, b in zip(current, home)) > self.config.position_tolerance_degrees:
                self._begin_transition(
                    current,
                    home,
                    self.config.initial_alignment_duration_seconds,
                    "ALIGNING",
                    target_waypoint_index=0,
                )
                self._set_status(
                    "Initial alignment to waypoint home started; this pre-roll is not part of the 14 s cycle"
                )
            else:
                self._adapter.set_positions_degrees(home)
                self._begin_cycle_segment(1)
        except Exception as exc:
            self._set_error(exc)

    def pause(self) -> None:
        try:
            if self._state not in MOVING_STATES:
                raise RuntimeError("Automation is not running")
            self._paused_from_state = self._state
            self._state = "PAUSED"
            if self._adapter is not None:
                self._adapter.clear_selected_velocities()
            self._set_status("Automation paused; existing data recording is not paused")
        except Exception as exc:
            self._set_error(exc, preserve_state=True)

    def resume(self) -> None:
        try:
            self._require_ready()
            if self._state != "PAUSED" or self._paused_from_state not in MOVING_STATES:
                raise RuntimeError("Automation is not paused")
            if self._manual_joint_motion_active():
                raise RuntimeError(
                    "The existing panel is moving arm joints; press its Stop button first"
                )
            assert self._adapter is not None
            current = self._adapter.get_positions_degrees()
            remaining = max(self._segment_duration - self._segment_elapsed, 1.0e-3)
            resume_state = self._paused_from_state
            self._begin_transition(
                current,
                self._segment_target,
                remaining,
                resume_state,
                self._target_waypoint_index,
            )
            self._set_status(f"Automation resumed; remaining segment time={remaining:.3f}s")
        except Exception as exc:
            self._set_error(exc, preserve_state=True)

    def stop(self) -> None:
        try:
            self._require_ready()
            if self._adapter is not None:
                self._adapter.clear_selected_velocities()
            self._state = "STOPPED"
            self._paused_from_state = None
            self._set_status(
                "Automation stopped; Cab and the existing recorder remain unchanged"
            )
        except Exception as exc:
            self._set_error(exc)

    def reload_config(self) -> None:
        try:
            if self._state in MOVING_STATES:
                raise RuntimeError("Pause or stop automation before reloading the JSON")
            self.config = load_automation_config(self.config_path)
            self._refresh_config_label()
            self.bind_current_stage()
            self._set_status("JSON reloaded; validating against the active Stage")
        except Exception as exc:
            self._set_error(exc, preserve_state=True)

    def _begin_cycle_segment(self, target_index: int) -> None:
        if not 1 <= target_index < len(self.config.waypoints):
            raise RuntimeError(f"Invalid cycle target waypoint index: {target_index}")
        assert self._adapter is not None
        target = self.config.waypoints[target_index]
        duration = float(target.duration_from_previous_seconds)
        self._begin_transition(
            self._adapter.get_positions_degrees(),
            target.angles_degrees,
            duration,
            "RUNNING",
            target_index,
        )
        self._set_status(
            f"Moving to {target.name}: duration={duration:g}s, "
            f"cycle={self._completed_cycles + 1}"
        )

    def _begin_transition(
        self,
        start: Sequence[float],
        target: Sequence[float],
        duration: float,
        state: str,
        target_waypoint_index: int,
    ) -> None:
        self._segment_start = tuple(float(value) for value in start)  # type: ignore[assignment]
        self._segment_target = tuple(float(value) for value in target)  # type: ignore[assignment]
        self._segment_duration = float(duration)
        self._segment_elapsed = 0.0
        self._target_waypoint_index = int(target_waypoint_index)
        self._state = state
        self._paused_from_state = None

    def _on_update(self, event: Any) -> None:
        if self._closed or self._adapter is None or self._stage is None:
            return
        try:
            if self._usd_context.get_stage() is not self._stage:
                self._release_binding()
                self._set_status("Stage changed; click Bind stage")
                return
            if not self._adapter.ready:
                if not self._timeline.is_playing():
                    self._timeline.play()
                    self._timeline.commit()
                return
            if not self._runtime_ready:
                self._validate_stage_limits()
                self._adapter.get_positions_degrees()
                self._runtime_ready = True
                self._state = "READY"
                self._set_status(
                    "Ready. Automation controls only Boom, Small arm and Bucket; Cab recording is retained"
                )
                return

            current = self._adapter.get_positions_degrees()
            self._angles_label.text = (
                f"Current: Boom={current[0]:.3f}, Small arm={current[1]:.3f}, "
                f"Bucket={current[2]:.3f} deg"
            )
            if self._state not in MOVING_STATES:
                self._refresh_motion_label()
                return
            if self._manual_joint_motion_active():
                self._paused_from_state = self._state
                self._state = "PAUSED"
                self._set_status(
                    "Automation paused because the existing panel started a manual arm-joint move"
                )
                return

            payload = event.payload if event.payload is not None else {}
            dt = float(payload.get("dt", 0.0))
            if not math.isfinite(dt) or dt <= 0:
                return
            self._segment_elapsed += dt
            normalized = min(self._segment_elapsed / self._segment_duration, 1.0)
            progress = self._interpolation_progress(normalized)
            commanded = tuple(
                start + (target - start) * progress
                for start, target in zip(self._segment_start, self._segment_target)
            )
            self._adapter.set_positions_degrees(commanded)
            self._refresh_motion_label(normalized)

            if normalized >= 1.0:
                self._adapter.set_positions_degrees(self._segment_target)
                if self._state == "ALIGNING":
                    self._begin_cycle_segment(1)
                else:
                    if self._target_waypoint_index == len(self.config.waypoints) - 1:
                        self._completed_cycles += 1
                        next_index = 1
                    else:
                        next_index = self._target_waypoint_index + 1
                    self._begin_cycle_segment(next_index)
        except Exception as exc:
            self._set_error(exc)

    def _interpolation_progress(self, normalized: float) -> float:
        if self.config.interpolation == "linear":
            return normalized
        return normalized * normalized * (3.0 - 2.0 * normalized)

    def _refresh_motion_label(self, normalized: float | None = None) -> None:
        if normalized is None:
            normalized = (
                min(self._segment_elapsed / self._segment_duration, 1.0)
                if self._segment_duration > 0
                else 0.0
            )
        target_name = (
            self.config.waypoints[self._target_waypoint_index].name
            if 0 <= self._target_waypoint_index < len(self.config.waypoints)
            else "--"
        )
        self._motion_label.text = (
            f"State: {self._state} | target={target_name} | "
            f"segment={self._segment_elapsed:.3f}/{self._segment_duration:.3f}s "
            f"({normalized * 100.0:.1f}%) | completed cycles={self._completed_cycles}"
        )

    def _require_ready(self) -> None:
        if not self._runtime_ready or self._adapter is None or not self._adapter.ready:
            raise RuntimeError("Automation is not ready; bind the stage and play the Timeline")

    def _set_status(self, text: str) -> None:
        self._status_label.text = text
        self._refresh_motion_label()
        print(f"[waji-joint-automation] {text}")

    def _set_error(self, exc: Exception, preserve_state: bool = False) -> None:
        if not preserve_state:
            self._state = "ERROR"
        self._set_status(f"ERROR: {exc}")

    def _release_binding(self) -> None:
        if self._adapter is not None:
            self._adapter.shutdown()
        self._adapter = None
        self._stage = None
        self._runtime_ready = False
        self._state = "UNBOUND"
        self._paused_from_state = None

    def _on_visibility_changed(self, visible: bool) -> None:
        if not visible:
            self.shutdown()

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._adapter is not None:
            self._adapter.clear_selected_velocities()
        self._release_binding()
        if self._update_subscription is not None:
            self._update_subscription.reset()
            self._update_subscription = None
        print("[waji-joint-automation] Panel shut down")


_ACTIVE_WINDOW: SynchronizedJointAutomationWindow | None = None


def show_automation_window(config_path: str | Path) -> SynchronizedJointAutomationWindow:
    """Replace any old instance and display the independent automation panel."""

    global _ACTIVE_WINDOW
    if _ACTIVE_WINDOW is not None:
        _ACTIVE_WINDOW.shutdown()
    _ACTIVE_WINDOW = SynchronizedJointAutomationWindow(config_path)
    return _ACTIVE_WINDOW
