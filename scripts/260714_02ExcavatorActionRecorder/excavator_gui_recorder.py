"""In-GUI excavator joint control, CSV recording, and trajectory playback."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from excavator_joint_controller import ExcavatorJointController
from joint_trajectory_recorder import (
    TrajectoryRecorder,
    resolve_csv_path,
    validate_csv_filename,
)
from trajectory import JOINT_NAMES, JointTrajectory


@dataclass(frozen=True)
class RecorderGuiConfig:
    csv_directory: Path
    csv_filename: str
    recording_enabled: bool = False
    playback_mode: str = "hold"
    safety_margin_degrees: float = 2.0

    def validated(self) -> "RecorderGuiConfig":
        validate_csv_filename(self.csv_filename)
        if self.playback_mode not in {"hold", "loop"}:
            raise ValueError("playback_mode must be 'hold' or 'loop'")
        return self

    @property
    def csv_path(self) -> Path:
        return resolve_csv_path(self.csv_directory, self.csv_filename)


class ExcavatorRecorderWindow:
    """Attach a responsive recorder panel to the currently running Isaac Sim GUI."""

    def __init__(self, config: RecorderGuiConfig) -> None:
        self.config = config.validated()

        # Import Kit APIs only after SimulationApp has started or inside an existing GUI.
        import omni.physx
        import omni.timeline
        import omni.ui as ui
        import omni.usd

        self._ui = ui
        self._usd_context = omni.usd.get_context()
        self._timeline = omni.timeline.get_timeline_interface()
        self._physx_interface = omni.physx.get_physx_interface()
        self._controller = ExcavatorJointController(
            safety_margin_degrees=self.config.safety_margin_degrees
        )
        self._trajectory: JointTrajectory | None = None
        self._loaded_path: Path | None = None
        self._recorder: TrajectoryRecorder | None = None
        self._record_elapsed = 0.0
        self._playback_elapsed = 0.0
        self._playback_active = False
        self._playback_paused = False
        self._updating_models = False
        self._desired_targets = {name: 0.0 for name in JOINT_NAMES}
        self._joint_models: dict[str, Any] = {}
        self._input_widgets: list[Any] = []
        self._closed = False

        self._bind_current_stage()
        self._create_models()
        self._build_window()
        self._physics_subscription = (
            self._physx_interface.subscribe_physics_step_events(self._on_physics_step)
        )
        self._set_status(f"Ready: {self.current_csv_path()}")

    @property
    def controller(self) -> ExcavatorJointController:
        return self._controller

    @property
    def record_sample_count(self) -> int:
        return self._recorder.sample_count if self._recorder is not None else 0

    def _bind_current_stage(self) -> None:
        stage = self._usd_context.get_stage()
        self._controller.bind(stage)
        self._desired_targets = self._controller.read_targets()

    def _create_models(self) -> None:
        ui = self._ui
        self._csv_dir_model = ui.SimpleStringModel(str(self.config.csv_directory))
        self._csv_name_model = ui.SimpleStringModel(self.config.csv_filename)
        self._record_enabled_model = ui.SimpleBoolModel(self.config.recording_enabled)
        self._loop_model = ui.SimpleBoolModel(self.config.playback_mode == "loop")
        for name in JOINT_NAMES:
            model = ui.SimpleFloatModel(self._desired_targets[name])
            model.add_value_changed_fn(
                lambda changed_model, joint_name=name: self._on_joint_model_changed(
                    joint_name, changed_model.as_float
                )
            )
            self._joint_models[name] = model

    def _build_window(self) -> None:
        ui = self._ui
        self._window = ui.Window(
            "Excavator Action Recorder", width=620, height=620, visible=True
        )
        self._window.set_visibility_changed_fn(self._on_visibility_changed)

        with self._window.frame:
            with ui.VStack(spacing=8, height=0):
                ui.Label("Excavator Action Recorder", height=28)
                ui.Separator()

                with ui.HStack(height=28):
                    ui.Label("CSV directory", width=120)
                    widget = ui.StringField(model=self._csv_dir_model)
                    self._input_widgets.append(widget)
                with ui.HStack(height=28):
                    ui.Label("CSV filename", width=120)
                    widget = ui.StringField(model=self._csv_name_model)
                    self._input_widgets.append(widget)
                with ui.HStack(height=28):
                    ui.Label("Enable recording", width=120)
                    widget = ui.CheckBox(model=self._record_enabled_model, width=24)
                    self._input_widgets.append(widget)
                    ui.Spacer()
                    ui.Label("Loop playback", width=110)
                    loop_widget = ui.CheckBox(model=self._loop_model, width=24)
                    self._input_widgets.append(loop_widget)

                self._path_label = ui.Label(str(self.current_csv_path()), height=36, word_wrap=True)
                with ui.HStack(height=30, spacing=6):
                    ui.Button("Refresh path", clicked_fn=self.refresh_path_label)
                    ui.Button("Rebind stage", clicked_fn=self.rebind_stage)
                    ui.Button("Reset home", clicked_fn=self.reset_home)

                ui.Separator()
                ui.Label("Joint target positions (degrees)", height=24)
                limits = self._controller.limits()
                for name in JOINT_NAMES:
                    lower, upper = limits[name]
                    with ui.HStack(height=30, spacing=6):
                        ui.Label(name, width=90)
                        slider = ui.FloatSlider(
                            model=self._joint_models[name], min=lower, max=upper
                        )
                        drag = ui.FloatDrag(
                            model=self._joint_models[name],
                            min=lower,
                            max=upper,
                            step=0.1,
                            width=110,
                        )
                        self._input_widgets.extend([slider, drag])
                        ui.Label(f"[{lower:.1f}, {upper:.1f}]", width=115)

                ui.Separator()
                with ui.HStack(height=34, spacing=6):
                    ui.Button("Start recording", clicked_fn=self.start_recording)
                    ui.Button("Stop recording", clicked_fn=self.stop_recording)
                with ui.HStack(height=34, spacing=6):
                    ui.Button("Load CSV", clicked_fn=self.load_trajectory)
                    ui.Button("Play / resume", clicked_fn=self.play_trajectory)
                    ui.Button("Pause", clicked_fn=self.pause_playback)
                    ui.Button("Stop", clicked_fn=self.stop_playback)

                self._status_label = ui.Label("Initializing...", height=72, word_wrap=True)

    def current_csv_path(self) -> Path:
        return resolve_csv_path(
            self._csv_dir_model.as_string,
            self._csv_name_model.as_string,
        )

    def refresh_path_label(self) -> None:
        try:
            path = self.current_csv_path()
            self._path_label.text = str(path)
            self._set_status(f"CSV path: {path}")
        except Exception as exc:
            self._set_error(exc)

    def rebind_stage(self) -> None:
        try:
            self._ensure_idle_for_stage_change()
            self._bind_current_stage()
            self._sync_models(self._desired_targets)
            self._set_status("Bound all four excavator joints to the current stage")
        except Exception as exc:
            self._set_error(exc)

    def reset_home(self) -> None:
        try:
            if self._playback_active or self._playback_paused:
                self.stop_playback()
            targets = self._controller.reset_home()
            self._desired_targets = targets
            self._sync_models(targets)
            self._set_status("Restored the Drive targets captured during stage binding")
        except Exception as exc:
            self._set_error(exc)

    def set_manual_target(self, name: str, value: float) -> None:
        """Set one target; also exposed for integration tests and scripted control."""

        if name not in JOINT_NAMES:
            raise ValueError(f"Unknown joint: {name}")
        targets = dict(self._desired_targets)
        targets[name] = float(value)
        targets = self._controller.set_targets(targets)
        self._desired_targets = targets
        self._sync_models(targets)

    def _on_joint_model_changed(self, name: str, value: float) -> None:
        if self._updating_models or self._closed:
            return
        if self._playback_active:
            self._set_status("Pause or stop playback before manual control")
            self._sync_models(self._desired_targets)
            return
        try:
            targets = dict(self._desired_targets)
            targets[name] = float(value)
            self._desired_targets = self._controller.set_targets(targets)
        except Exception as exc:
            self._set_error(exc)
            self._sync_models(self._desired_targets)

    def start_recording(self) -> bool:
        try:
            if not self._record_enabled_model.as_bool:
                raise RuntimeError("Recording is disabled; enable it before starting")
            if self._recorder is not None and self._recorder.active:
                raise RuntimeError("Recording is already active")
            if self._playback_active or self._playback_paused:
                raise RuntimeError("Stop playback before recording")

            path = self.current_csv_path()
            self._path_label.text = str(path)
            recorder = TrajectoryRecorder(path)
            recorder.start(self._controller.read_targets())
            self._recorder = recorder
            self._record_elapsed = 0.0
            self._set_path_inputs_enabled(False)
            self._timeline.play()
            self._timeline.commit()
            self._set_status(f"Recording started: {recorder.partial_path}")
            return True
        except Exception as exc:
            self._set_error(exc)
            return False

    def stop_recording(self) -> Path | None:
        try:
            if self._recorder is None or not self._recorder.active:
                raise RuntimeError("Recording is not active")
            final_path = self._recorder.stop()
            count = self._recorder.sample_count
            self._set_path_inputs_enabled(True)
            self._set_status(
                f"Recording complete: {final_path} ({count} samples, "
                f"{self._record_elapsed:.6f}s)"
            )
            return final_path
        except Exception as exc:
            self._set_path_inputs_enabled(True)
            self._set_error(exc)
            return None

    def load_trajectory(self) -> JointTrajectory | None:
        try:
            if self._recorder is not None and self._recorder.active:
                raise RuntimeError("Stop recording before loading a trajectory")
            path = self.current_csv_path()
            trajectory = JointTrajectory.from_csv(path)
            self._controller.validate_trajectory(trajectory)
            if self._loop_model.as_bool:
                first = trajectory.keyframes[0].targets
                last = trajectory.keyframes[-1].targets
                if any(abs(first[name] - last[name]) > 1e-9 for name in JOINT_NAMES):
                    raise ValueError("Loop playback requires identical first and last targets")
            self._trajectory = trajectory
            self._loaded_path = path
            self._playback_elapsed = 0.0
            self._playback_active = False
            self._playback_paused = False
            self._set_status(
                f"Loaded {len(trajectory.keyframes)} samples, "
                f"duration={trajectory.duration:.6f}s"
            )
            return trajectory
        except Exception as exc:
            self._set_error(exc)
            return None

    def play_trajectory(self) -> bool:
        try:
            if self._recorder is not None and self._recorder.active:
                raise RuntimeError("Stop recording before playback")
            path = self.current_csv_path()
            if self._trajectory is None or self._loaded_path != path:
                if self.load_trajectory() is None:
                    return False
            if not self._playback_paused:
                self._playback_elapsed = 0.0
                _, targets = self._trajectory.sample(0.0, self._playback_mode())
                self._desired_targets = self._controller.set_targets(targets)
                self._sync_models(targets)
            self._playback_active = True
            self._playback_paused = False
            self._set_path_inputs_enabled(False)
            self._timeline.play()
            self._timeline.commit()
            self._set_status(f"Playback running: {path}")
            return True
        except Exception as exc:
            self._set_error(exc)
            return False

    def pause_playback(self) -> None:
        if not self._playback_active:
            self._set_status("Playback is not running")
            return
        self._playback_active = False
        self._playback_paused = True
        self._timeline.pause()
        self._timeline.commit()
        self._set_path_inputs_enabled(True)
        self._set_status(f"Playback paused at {self._playback_elapsed:.6f}s")

    def stop_playback(self) -> None:
        self._playback_active = False
        self._playback_paused = False
        self._playback_elapsed = 0.0
        self._timeline.pause()
        self._timeline.commit()
        self._set_path_inputs_enabled(True)
        if self._trajectory is not None:
            _, targets = self._trajectory.sample(0.0, self._playback_mode())
            self._desired_targets = self._controller.set_targets(targets)
            self._sync_models(targets)
        self._set_status("Playback stopped")

    def _on_physics_step(self, step_seconds: float) -> None:
        if self._closed:
            return
        try:
            current_stage = self._usd_context.get_stage()
            if current_stage is not self._controller.stage:
                raise RuntimeError("USD stage changed; stop and rebind the recorder")

            dt = float(step_seconds)
            if dt <= 0:
                return

            if self._playback_active and self._trajectory is not None:
                self._playback_elapsed += dt
                mode = self._playback_mode()
                _, targets = self._trajectory.sample(self._playback_elapsed, mode)
                self._desired_targets = self._controller.set_targets(targets)
                self._sync_models(targets)
                if mode == "hold" and self._playback_elapsed >= self._trajectory.duration:
                    self._playback_active = False
                    self._playback_paused = False
                    self._timeline.pause()
                    self._timeline.commit()
                    self._set_path_inputs_enabled(True)
                    self._set_status("Playback complete; final target is held")
            else:
                self._desired_targets = self._controller.set_targets(self._desired_targets)

            if self._recorder is not None and self._recorder.active:
                self._record_elapsed += dt
                self._recorder.record_sample(
                    self._record_elapsed, self._controller.read_targets()
                )
                if self._recorder.sample_count % 30 == 0:
                    self._set_status(
                        f"Recording: {self._recorder.sample_count} samples, "
                        f"{self._record_elapsed:.6f}s"
                    )
        except Exception as exc:
            if self._recorder is not None and self._recorder.active:
                self._recorder.abort()
            self._playback_active = False
            self._playback_paused = False
            self._set_path_inputs_enabled(True)
            self._set_error(exc)

    def _playback_mode(self) -> str:
        return "loop" if self._loop_model.as_bool else "hold"

    def _sync_models(self, targets: dict[str, float]) -> None:
        self._updating_models = True
        try:
            for name in JOINT_NAMES:
                self._joint_models[name].set_value(float(targets[name]))
        finally:
            self._updating_models = False

    def _set_path_inputs_enabled(self, enabled: bool) -> None:
        for widget in self._input_widgets[:4]:
            widget.enabled = enabled

    def _set_status(self, text: str) -> None:
        if hasattr(self, "_status_label"):
            self._status_label.text = text
        print(f"[excavator-recorder] {text}")

    def _set_error(self, exc: Exception) -> None:
        self._set_status(f"ERROR: {exc}")

    def _ensure_idle_for_stage_change(self) -> None:
        if self._recorder is not None and self._recorder.active:
            raise RuntimeError("Stop recording before rebinding the stage")
        if self._playback_active or self._playback_paused:
            raise RuntimeError("Stop playback before rebinding the stage")

    def _on_visibility_changed(self, visible: bool) -> None:
        if not visible:
            self.shutdown()

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._recorder is not None and self._recorder.active:
            partial = self._recorder.abort()
            print(f"[excavator-recorder] Recording aborted; partial file: {partial}")
        self._playback_active = False
        self._playback_paused = False
        self._physics_subscription = None


_ACTIVE_WINDOW: ExcavatorRecorderWindow | None = None


def show_recorder_window(config: RecorderGuiConfig) -> ExcavatorRecorderWindow:
    """Create one panel in an already-running Isaac Sim GUI."""

    global _ACTIVE_WINDOW
    if _ACTIVE_WINDOW is not None:
        _ACTIVE_WINDOW.shutdown()
    _ACTIVE_WINDOW = ExcavatorRecorderWindow(config)
    return _ACTIVE_WINDOW

