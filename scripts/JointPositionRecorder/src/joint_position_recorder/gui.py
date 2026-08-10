"""Isaac Sim GUI panel for direct articulation positioning and actual-angle recording."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .articulation_adapter import IsaacArticulationAdapter
from .config import ProjectConfig
from .controller import (
    ROOT_ORIENTATION_COLUMNS,
    ROOT_WORLD_POSITION_COLUMNS,
    ControllerSnapshot,
    MotionController,
    MotionState,
)
from .root_motion import (
    euler_xyz_degrees_from_quaternion_wxyz,
    yaw_degrees_from_quaternion_wxyz,
)
from .stage_validator import StageValidationReport, validate_stage
from .trajectory_recorder import resolve_csv_path


_ISAAC_FOCUS_ACTION_EXT_ID = "isaacsim.gui.menu.edit_menu"
_ISAAC_FOCUS_ACTION_ID = "focus_prim"


class JointPositionRecorderWindow:
    """Attach an independent four-joint recorder panel to the current Isaac Sim GUI."""

    def __init__(self, config: ProjectConfig, project_root: Path) -> None:
        import carb
        import carb.eventdispatcher
        import omni.kit.app
        import omni.appwindow
        import omni.timeline
        import omni.ui as ui
        import omni.usd
        from omni.kit.actions.core import get_action_registry

        self.config = config
        self.project_root = Path(project_root).resolve()
        self._ui = ui
        self._usd_context = omni.usd.get_context()
        self._timeline = omni.timeline.get_timeline_interface()
        self._carb = carb
        self._input_interface = carb.input.acquire_input_interface()
        app_window = omni.appwindow.get_default_app_window()
        self._keyboard = app_window.get_keyboard() if app_window is not None else None
        self._keyboard_subscription = None
        self._pressed_drive_keys: set[str] = set()
        self._action_registry = get_action_registry()
        self._suppressed_focus_action = None
        self._focus_action_override = None
        self._wasd_enabled_change_id = None
        self._stage = None
        self._report: StageValidationReport | None = None
        self._adapter: IsaacArticulationAdapter | None = None
        self._controller: MotionController | None = None
        self._runtime_validated = False
        self._closed = False
        self._target_models: dict[str, Any] = {}
        self._speed_models: dict[str, Any] = {}
        self._current_labels: dict[str, Any] = {}
        self._joint_status_labels: dict[str, Any] = {}
        self._build_window()
        if self.config.root_motion.enabled:
            if self._keyboard is None:
                raise RuntimeError("Cannot acquire the Isaac Sim keyboard")
            self._wasd_enabled_change_id = self._wasd_enabled_model.add_value_changed_fn(
                self._on_wasd_enabled_changed
            )
            self._suppress_isaac_focus_action()
            self._keyboard_subscription = self._input_interface.subscribe_to_keyboard_events(
                self._keyboard, self._on_keyboard_event
            )
        self._update_subscription = carb.eventdispatcher.get_eventdispatcher().observe_event(
            event_name=omni.kit.app.GLOBAL_EVENT_UPDATE,
            on_event=self._on_update,
            observer_name="joint-position-recorder-update",
        )
        self.bind_current_stage()

    def _build_window(self) -> None:
        ui = self._ui
        self._window = ui.Window(
            "Excavator WASD+FG and Joint Controller", width=850, height=830, visible=True
        )
        self._window.set_visibility_changed_fn(self._on_visibility_changed)
        default_directory = self.config.resolve_csv_directory(self.project_root)
        self._csv_directory_model = ui.SimpleStringModel(str(default_directory))
        self._csv_filename_model = ui.SimpleStringModel(self.config.default_csv_filename)

        with self._window.frame:
            with ui.VStack(spacing=8, height=0):
                ui.Label("Direct Articulation Position Control", height=28)
                ui.Label(f"Profile: {self.config.profile_name}", height=22)
                self._root_label = ui.Label("Articulation root: not bound", height=22)
                ui.Separator()

                with ui.HStack(height=28, spacing=8):
                    ui.Label("Joint", width=120)
                    ui.Label("Current (deg)", width=140)
                    ui.Label("Target (deg)", width=170)
                    ui.Label("Speed (deg/s)", width=170)
                    ui.Label("State", width=120)

                for joint in self.config.joints:
                    with ui.HStack(height=32, spacing=8):
                        ui.Label(joint.display_name, width=120)
                        current = ui.Label("--", width=140)
                        target_model = ui.SimpleFloatModel(joint.home_degrees)
                        speed_model = ui.SimpleFloatModel(joint.default_speed_degrees)
                        ui.FloatDrag(model=target_model, step=0.1, width=170)
                        ui.FloatDrag(model=speed_model, min=0.001, step=0.1, width=170)
                        state = ui.Label("Unbound", width=120)
                    self._current_labels[joint.logical_name] = current
                    self._target_models[joint.logical_name] = target_model
                    self._speed_models[joint.logical_name] = speed_model
                    self._joint_status_labels[joint.logical_name] = state

                ui.Separator()
                with ui.HStack(height=36, spacing=6):
                    ui.Button("Bind current stage", clicked_fn=self.bind_current_stage)
                    ui.Button("Move all", clicked_fn=self.move_all)
                    ui.Button("Stop", clicked_fn=self.stop_motion)
                    ui.Button("Targets = current", clicked_fn=self.reset_targets)
                    ui.Button("Move home", clicked_fn=self.move_home)

                ui.Separator()
                ui.Label("Floating-base WASD+FG Control", height=24)
                self._wasd_enabled_model = ui.SimpleBoolModel(
                    self.config.root_motion.enabled
                )
                self._linear_speed_model = ui.SimpleFloatModel(
                    self.config.root_motion.linear_speed_meters_per_second
                )
                self._angular_speed_model = ui.SimpleFloatModel(
                    self.config.root_motion.angular_speed_degrees_per_second
                )
                self._vertical_speed_model = ui.SimpleFloatModel(
                    self.config.root_motion.vertical_speed_meters_per_second
                )
                with ui.HStack(height=30, spacing=8):
                    ui.Label("WASD+FG enabled", width=120)
                    ui.CheckBox(model=self._wasd_enabled_model, width=30)
                    ui.Label(
                        "W/S: Local X +/-   A/D: turn   F/G: Local Z +/-",
                        width=450,
                    )
                    ui.Button("Stop root", clicked_fn=self.stop_root_motion, width=120)
                with ui.HStack(height=30, spacing=8):
                    ui.Label("Linear (m/s)", width=120)
                    ui.FloatDrag(
                        model=self._linear_speed_model,
                        min=0.001,
                        step=0.05,
                        width=170,
                    )
                    ui.Label("Turn (deg/s)", width=120)
                    ui.FloatDrag(
                        model=self._angular_speed_model,
                        min=0.001,
                        step=1.0,
                        width=170,
                    )
                with ui.HStack(height=30, spacing=8):
                    ui.Label("Vertical (m/s)", width=120)
                    ui.FloatDrag(
                        model=self._vertical_speed_model,
                        min=0.001,
                        step=0.05,
                        width=170,
                    )
                    ui.Label("F: Local Z+ up    G: Local Z- down", width=420)
                self._root_pose_label = ui.Label(
                    "Root pose: --", height=24, word_wrap=True
                )
                self._wasd_state_label = ui.Label(
                    "WASD+FG: idle", height=22
                )

                ui.Separator()
                with ui.HStack(height=28, spacing=6):
                    ui.Label("CSV directory", width=120)
                    ui.StringField(model=self._csv_directory_model)
                with ui.HStack(height=28, spacing=6):
                    ui.Label("CSV filename", width=120)
                    ui.StringField(model=self._csv_filename_model)
                with ui.HStack(height=36, spacing=6):
                    ui.Button("Start recording", clicked_fn=self.start_recording)
                    ui.Button("Stop recording", clicked_fn=self.stop_recording)

                self._status_label = ui.Label(
                    "Initializing...", height=92, word_wrap=True
                )

    def bind_current_stage(self) -> None:
        try:
            self._release_binding(abort_recording=True)
            stage = self._usd_context.get_stage()
            report = validate_stage(stage, self.config)
            if not report.ok:
                details = " | ".join(issue.format() for issue in report.errors)
                raise RuntimeError(details)
            report.require_valid()
            ordered_dof_names = tuple(
                report.dof_names[joint.logical_name] for joint in self.config.joints
            )
            adapter = IsaacArticulationAdapter(
                report.articulation_root_path or "", ordered_dof_names
            )
            adapter.bind()
            controller = MotionController(self.config, adapter, report.limits_degrees)
            self._stage = stage
            self._report = report
            self._adapter = adapter
            self._controller = controller
            self._runtime_validated = False
            self._root_label.text = f"Articulation root: {report.articulation_root_path}"
            if not self._timeline.is_playing():
                self._timeline.play()
                self._timeline.commit()
            self._set_status("Stage validated; waiting for the Articulation physics tensor")
        except Exception as exc:
            self._set_error(exc)

    def move_all(self) -> None:
        try:
            controller = self._require_controller()
            targets = {
                name: model.as_float for name, model in self._target_models.items()
            }
            speeds = {name: model.as_float for name, model in self._speed_models.items()}
            snapshot = controller.start_motion(targets, speeds)
            self._refresh_snapshot(snapshot)
            self._set_status("Motion started with independent constant joint speeds")
        except Exception as exc:
            self._set_error(exc)

    def stop_motion(self) -> None:
        try:
            snapshot = self._require_controller().stop_motion()
            self._write_targets(snapshot.current_degrees)
            self._refresh_snapshot(snapshot)
            self._set_status("Motion stopped; current articulation position is held")
        except Exception as exc:
            self._set_error(exc)

    def stop_root_motion(self) -> None:
        """Stop only the floating base; an active joint target remains active."""

        try:
            self._pressed_drive_keys.clear()
            controller = self._require_controller()
            snapshot = controller.stop_root_motion()
            self._refresh_snapshot(snapshot)
            self._set_status("WASD+FG root motion stopped; joint control is unchanged")
        except Exception as exc:
            self._set_error(exc)

    def reset_targets(self) -> None:
        try:
            snapshot = self._require_controller().reset_targets_to_current()
            self._write_targets(snapshot.current_degrees)
            self._refresh_snapshot(snapshot)
            self._set_status("Targets reset to current articulation positions")
        except Exception as exc:
            self._set_error(exc)

    def move_home(self) -> None:
        try:
            controller = self._require_controller()
            speeds = {name: model.as_float for name, model in self._speed_models.items()}
            targets = {
                joint.logical_name: joint.home_degrees for joint in self.config.joints
            }
            self._write_targets(targets)
            snapshot = controller.start_motion(targets, speeds)
            self._refresh_snapshot(snapshot)
            self._set_status("Moving to configured home angles")
        except Exception as exc:
            self._set_error(exc)

    def start_recording(self) -> None:
        try:
            controller = self._require_controller()
            output = resolve_csv_path(
                self._csv_directory_model.as_string,
                self._csv_filename_model.as_string,
            )
            report = self._report
            metadata = {
                "profile": self.config.profile_name,
                "control_mode": (
                    "articulation_direct_joint_position_and_root_pose"
                    if self.config.root_motion.enabled
                    else "articulation_direct_joint_position"
                ),
                "angle_unit": "degree",
                "speed_unit": "degree_per_second",
                "root_motion_enabled": self.config.root_motion.enabled,
                "root_linear_speed_meters_per_second": (
                    self._linear_speed_model.as_float
                    if self.config.root_motion.enabled
                    else None
                ),
                "root_angular_speed_degrees_per_second": (
                    self._angular_speed_model.as_float
                    if self.config.root_motion.enabled
                    else None
                ),
                "root_vertical_speed_meters_per_second": (
                    self._vertical_speed_model.as_float
                    if self.config.root_motion.enabled
                    else None
                ),
                "recorded_root_orientation_columns": (
                    list(ROOT_ORIENTATION_COLUMNS)
                    if self.config.root_motion.enabled
                    else []
                ),
                "recorded_root_world_position_columns": (
                    list(ROOT_WORLD_POSITION_COLUMNS)
                    if self.config.root_motion.enabled
                    else []
                ),
                "root_quaternion_order": (
                    "wxyz" if self.config.root_motion.enabled else None
                ),
                "root_euler_angles": (
                    {
                        "order": ["roll_x_deg", "pitch_y_deg", "yaw_z_deg"],
                        "convention": "Rz(yaw) * Ry(pitch) * Rx(roll)",
                        "unit": "degree",
                        "yaw_range": "[-180, 180]",
                    }
                    if self.config.root_motion.enabled
                    else None
                ),
                "articulation_root": report.articulation_root_path if report else None,
                "joint_paths": report.joint_paths if report else {},
                "dof_names": report.dof_names if report else {},
                "stage": self._stage.GetRootLayer().identifier if self._stage else None,
            }
            partial = controller.start_recording(output, metadata)
            content = (
                "joint angles, root world position, and root quaternion/Euler angles"
                if self.config.root_motion.enabled
                else "actual articulation angles"
            )
            self._set_status(f"Recording {content}: {partial}")
        except Exception as exc:
            self._set_error(exc)

    def stop_recording(self) -> None:
        try:
            controller = self._require_controller()
            snapshot = controller.snapshot()
            final_root_euler = (
                euler_xyz_degrees_from_quaternion_wxyz(
                    snapshot.root_orientation_wxyz
                )
                if snapshot.root_orientation_wxyz is not None
                else None
            )
            output = controller.stop_recording(
                {
                    "final_motion_state": snapshot.state.value,
                    "final_targets_degrees": dict(snapshot.target_degrees),
                    "commanded_speeds_degrees_per_second": dict(
                        snapshot.speed_degrees_per_second
                    ),
                    "final_root_orientation_wxyz": (
                        list(snapshot.root_orientation_wxyz)
                        if snapshot.root_orientation_wxyz is not None
                        else None
                    ),
                    "final_root_euler_xyz_degrees": (
                        list(final_root_euler) if final_root_euler is not None else None
                    ),
                }
            )
            self._set_status(f"Recording complete: {output}")
        except Exception as exc:
            self._set_error(exc)

    def _on_update(self, event: Any) -> None:
        if self._closed or self._controller is None or self._adapter is None:
            return
        try:
            if self._usd_context.get_stage() is not self._stage:
                self._release_binding(abort_recording=True)
                self._set_status("Stage changed; bind the current stage again")
                return
            if not self._adapter.ready:
                if not self._timeline.is_playing():
                    self._timeline.play()
                    self._timeline.commit()
                return
            if not self._runtime_validated:
                self._adapter.validate_runtime()
                snapshot = self._controller.synchronize()
                self._write_targets(snapshot.current_degrees)
                self._refresh_snapshot(snapshot)
                self._runtime_validated = True
                root_text = " with WASD+FG root motion" if self.config.root_motion.enabled else ""
                self._set_status(f"Ready: 4-DOF Articulation is initialized{root_text}")
                return
            payload = event.payload if event.payload is not None else {}
            dt = float(payload.get("dt", 0.0))
            self._apply_root_motion_input()
            snapshot = self._controller.update(dt)
            self._refresh_snapshot(snapshot)
        except Exception as exc:
            if self._controller is not None:
                self._controller.fail()
            self._set_error(exc)

    def _refresh_snapshot(self, snapshot: ControllerSnapshot) -> None:
        for name in self.config.logical_joint_names:
            self._current_labels[name].text = f"{snapshot.current_degrees[name]:.4f}"
            if snapshot.state is MotionState.MOVING:
                text = "Reached" if snapshot.joint_reached[name] else "Moving"
            elif snapshot.state is MotionState.ERROR:
                text = "Error"
            else:
                text = snapshot.state.value.title()
            self._joint_status_labels[name].text = text
        if snapshot.root_position_meters is not None and snapshot.root_orientation_wxyz is not None:
            x, y, z = snapshot.root_position_meters
            yaw = yaw_degrees_from_quaternion_wxyz(snapshot.root_orientation_wxyz)
            self._root_pose_label.text = (
                f"Root world pose: x={x:.3f} m, y={y:.3f} m, z={z:.3f} m, "
                f"yaw={yaw:.2f} deg"
            )
        else:
            self._root_pose_label.text = "Root pose: root motion disabled by profile"
        keys = "+".join(sorted(self._pressed_drive_keys)) or "idle"
        self._wasd_state_label.text = (
            f"WASD+FG: {keys} | forward={snapshot.root_forward_axis:+.0f}, "
            f"turn={snapshot.root_turn_axis:+.0f}, "
            f"vertical={snapshot.root_vertical_axis:+.0f}"
        )

    def _on_keyboard_event(self, event: Any) -> bool:
        key = getattr(event.input, "name", str(event.input).split(".")[-1]).upper()
        if key not in {"W", "A", "S", "D", "F", "G"}:
            return False
        if not self._wasd_enabled_model.as_bool:
            return False
        event_type = event.type
        if event_type in {
            self._carb.input.KeyboardEventType.KEY_PRESS,
            self._carb.input.KeyboardEventType.KEY_REPEAT,
        }:
            self._pressed_drive_keys.add(key)
            return True
        elif event_type == self._carb.input.KeyboardEventType.KEY_RELEASE:
            self._pressed_drive_keys.discard(key)
            return True
        return False

    def _on_wasd_enabled_changed(self, model: Any) -> None:
        """Reserve F for vertical control only while root keyboard input is enabled."""

        if model.as_bool:
            self._suppress_isaac_focus_action()
        else:
            self._pressed_drive_keys.clear()
            self._restore_isaac_focus_action()

    def _suppress_isaac_focus_action(self) -> None:
        """Temporarily replace Isaac Sim's Focus action with a runtime no-op.

        The regular keyboard subscription and Kit's hotkey system are independent;
        consuming a Carb keyboard event does not prevent the global ``focus_prim``
        action from running.  Keep the F Hotkey object unchanged so Edit-menu refreshes
        remain conflict-free, preserve the exact original Action without invalidating
        it, and temporarily register a no-op Action under the same identifier.  This
        changes no persistent hotkey settings and lets shutdown restore the original
        Action object exactly.
        """

        if self._action_registry is None or self._suppressed_focus_action is not None:
            return
        original_action = self._action_registry.get_action(
            _ISAAC_FOCUS_ACTION_EXT_ID, _ISAAC_FOCUS_ACTION_ID
        )
        if original_action is None:
            raise RuntimeError("Isaac Sim Focus action is unavailable")
        self._action_registry.deregister_action(
            original_action, invalidate=False
        )
        if self._action_registry.get_action(
            _ISAAC_FOCUS_ACTION_EXT_ID, _ISAAC_FOCUS_ACTION_ID
        ) is not None:
            raise RuntimeError("Could not temporarily remove Isaac Sim's Focus action")
        self._suppressed_focus_action = original_action
        try:
            self._focus_action_override = self._action_registry.register_action(
                _ISAAC_FOCUS_ACTION_EXT_ID,
                _ISAAC_FOCUS_ACTION_ID,
                self._consume_reserved_f_action,
                display_name=original_action.display_name,
                description=original_action.description,
                icon_url=original_action.icon_url,
                tag=original_action.tag,
            )
            if self._focus_action_override is None:
                raise RuntimeError("Could not register the temporary Focus no-op action")
        except Exception:
            self._restore_isaac_focus_action()
            raise

        print(
            "[joint-position-recorder] Isaac Sim F/Focus action is temporarily "
            "reserved for Local Z+ motion"
        )

    @staticmethod
    def _consume_reserved_f_action() -> None:
        """No-op action; root motion is handled by the Carb keyboard callback."""

    def _restore_isaac_focus_action(self) -> None:
        """Remove the runtime no-op and restore the exact original Focus Action."""

        if self._action_registry is None or self._suppressed_focus_action is None:
            return
        original_action = self._suppressed_focus_action
        current_action = self._action_registry.get_action(
            _ISAAC_FOCUS_ACTION_EXT_ID, _ISAAC_FOCUS_ACTION_ID
        )
        if current_action is self._focus_action_override:
            self._action_registry.deregister_action(current_action)
            current_action = None
        self._focus_action_override = None

        if current_action is None:
            self._action_registry.register_action(original_action)
            restored_action = self._action_registry.get_action(
                _ISAAC_FOCUS_ACTION_EXT_ID, _ISAAC_FOCUS_ACTION_ID
            )
            if restored_action is not original_action:
                print(
                    "[joint-position-recorder] WARNING: Could not restore Isaac Sim "
                    "F/Focus action"
                )
                return
        elif current_action is not original_action:
            print(
                "[joint-position-recorder] WARNING: Another Focus action appeared; "
                "the panel left it unchanged"
            )
            return

        self._suppressed_focus_action = None
        print("[joint-position-recorder] Isaac Sim F/Focus action restored")

    def _apply_root_motion_input(self) -> None:
        if self._controller is None or not self.config.root_motion.enabled:
            return
        if not self._wasd_enabled_model.as_bool:
            self._pressed_drive_keys.clear()
            self._controller.set_root_motion_input(0.0, 0.0, 0.0)
            return
        forward_axis = float("W" in self._pressed_drive_keys) - float(
            "S" in self._pressed_drive_keys
        )
        turn_axis = float("A" in self._pressed_drive_keys) - float(
            "D" in self._pressed_drive_keys
        )
        vertical_axis = float("F" in self._pressed_drive_keys) - float(
            "G" in self._pressed_drive_keys
        )
        linear_speed = self._linear_speed_model.as_float
        angular_speed = self._angular_speed_model.as_float
        vertical_speed = self._vertical_speed_model.as_float
        if linear_speed <= 0 or angular_speed <= 0 or vertical_speed <= 0:
            raise ValueError("WASD+FG linear, turn, and vertical speeds must be positive")
        # GUI speed values are intentionally live, so users can tune motion while driving.
        self._controller.set_root_motion_speeds(
            linear_speed,
            angular_speed,
            vertical_speed,
        )
        self._controller.set_root_motion_input(
            forward_axis,
            turn_axis,
            vertical_axis,
        )

    def _write_targets(self, values: Any) -> None:
        for name in self.config.logical_joint_names:
            self._target_models[name].set_value(float(values[name]))

    def _require_controller(self) -> MotionController:
        if self._controller is None or not self._runtime_validated:
            raise RuntimeError("Articulation is not ready; bind the stage and wait for initialization")
        return self._controller

    def _set_status(self, text: str) -> None:
        self._status_label.text = text
        print(f"[joint-position-recorder] {text}")

    def _set_error(self, exc: Exception) -> None:
        self._set_status(f"ERROR: {exc}")

    def _release_binding(self, abort_recording: bool) -> None:
        self._pressed_drive_keys.clear()
        if self._controller is not None and abort_recording:
            partial = self._controller.abort_recording()
            if partial is not None:
                print(f"[joint-position-recorder] Recording aborted; partial retained: {partial}")
        if self._adapter is not None:
            self._adapter.shutdown()
        self._controller = None
        self._adapter = None
        self._report = None
        self._stage = None
        self._runtime_validated = False

    def _on_visibility_changed(self, visible: bool) -> None:
        if not visible:
            self.shutdown()

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._release_binding(abort_recording=True)
        if self._keyboard_subscription is not None and self._keyboard is not None:
            self._input_interface.unsubscribe_to_keyboard_events(
                self._keyboard, self._keyboard_subscription
            )
            self._keyboard_subscription = None
        if self._wasd_enabled_change_id is not None:
            self._wasd_enabled_model.remove_value_changed_fn(
                self._wasd_enabled_change_id
            )
            self._wasd_enabled_change_id = None
        self._restore_isaac_focus_action()
        if self._update_subscription is not None:
            self._update_subscription.reset()
            self._update_subscription = None
        print("[joint-position-recorder] Panel shut down")


_ACTIVE_WINDOW: JointPositionRecorderWindow | None = None


def show_recorder_window(
    config: ProjectConfig, project_root: str | Path
) -> JointPositionRecorderWindow:
    """Replace any previous instance and show the independent recorder panel."""

    global _ACTIVE_WINDOW
    if _ACTIVE_WINDOW is not None:
        _ACTIVE_WINDOW.shutdown()
    _ACTIVE_WINDOW = JointPositionRecorderWindow(config, Path(project_root))
    return _ACTIVE_WINDOW
