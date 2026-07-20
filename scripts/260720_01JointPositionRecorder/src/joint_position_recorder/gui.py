"""Isaac Sim GUI panel for direct articulation positioning and actual-angle recording."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .articulation_adapter import IsaacArticulationAdapter
from .config import ProjectConfig
from .controller import ControllerSnapshot, MotionController, MotionState
from .stage_validator import StageValidationReport, validate_stage
from .trajectory_recorder import resolve_csv_path


class JointPositionRecorderWindow:
    """Attach an independent four-joint recorder panel to the current Isaac Sim GUI."""

    def __init__(self, config: ProjectConfig, project_root: Path) -> None:
        import omni.kit.app
        import omni.timeline
        import omni.ui as ui
        import omni.usd

        self.config = config
        self.project_root = Path(project_root).resolve()
        self._ui = ui
        self._usd_context = omni.usd.get_context()
        self._timeline = omni.timeline.get_timeline_interface()
        self._app = omni.kit.app.get_app()
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
        self._update_subscription = (
            self._app.get_update_event_stream().create_subscription_to_pop(
                self._on_update, name="joint-position-recorder-update"
            )
        )
        self.bind_current_stage()

    def _build_window(self) -> None:
        ui = self._ui
        self._window = ui.Window(
            "Articulation Joint Position Recorder", width=850, height=660, visible=True
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
                "control_mode": "articulation_direct_position",
                "angle_unit": "degree",
                "speed_unit": "degree_per_second",
                "articulation_root": report.articulation_root_path if report else None,
                "joint_paths": report.joint_paths if report else {},
                "dof_names": report.dof_names if report else {},
                "stage": self._stage.GetRootLayer().identifier if self._stage else None,
            }
            partial = controller.start_recording(output, metadata)
            self._set_status(f"Recording actual articulation angles: {partial}")
        except Exception as exc:
            self._set_error(exc)

    def stop_recording(self) -> None:
        try:
            controller = self._require_controller()
            snapshot = controller.snapshot()
            output = controller.stop_recording(
                {
                    "final_motion_state": snapshot.state.value,
                    "final_targets_degrees": dict(snapshot.target_degrees),
                    "commanded_speeds_degrees_per_second": dict(
                        snapshot.speed_degrees_per_second
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
                self._set_status("Ready: 4-DOF Articulation is initialized")
                return
            payload = event.payload if event.payload is not None else {}
            dt = float(payload.get("dt", 0.0))
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
