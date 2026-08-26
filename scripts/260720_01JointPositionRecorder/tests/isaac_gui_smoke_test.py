"""Create the real recorder window and verify automatic stage binding."""

from __future__ import annotations

import argparse
import csv
import json
import runpy
import tempfile
import traceback
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--usd", required=True)
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    from isaacsim import SimulationApp

    simulation_app = SimulationApp({"headless": args.headless})
    recording_temp: tempfile.TemporaryDirectory[str] | None = None
    try:
        import omni.usd

        project_root = Path(__file__).resolve().parents[1]
        context = omni.usd.get_context()
        if not context.open_stage(str(Path(args.usd).expanduser().resolve())):
            raise RuntimeError(f"Failed to open USD: {args.usd}")
        for _ in range(20):
            simulation_app.update()

        runpy.run_path(str(project_root / "entrypoints" / "show_panel.py"))
        from joint_position_recorder.controller import MotionState
        from joint_position_recorder.trajectory_recorder import RecordingState
        from joint_position_recorder import gui

        window = gui._ACTIVE_WINDOW
        if window is None:
            raise RuntimeError("Entrypoint did not create the recorder window")
        for _ in range(240):
            simulation_app.update()
            if window._runtime_validated:
                break
        if not window._runtime_validated or window._controller is None:
            raise RuntimeError(f"Panel did not bind successfully: {window._status_label.text}")
        snapshot = window._controller.snapshot()
        if snapshot.state is not MotionState.IDLE:
            raise AssertionError(f"Expected IDLE after binding, got {snapshot.state}")

        initial = dict(snapshot.current_degrees)
        recording_temp = tempfile.TemporaryDirectory(prefix="joint-recorder-gui-smoke-")
        recording_output = Path(recording_temp.name) / "pause_resume.csv"
        window._csv_directory_model.set_value(recording_temp.name)
        window._csv_filename_model.set_value(recording_output.name)
        window.start_recording()
        for _ in range(3):
            simulation_app.update()
        before_pause = window._controller.snapshot()
        if (
            before_pause.recording_state is not RecordingState.RECORDING
            or before_pause.recorded_samples < 2
        ):
            raise AssertionError(f"Recording did not start correctly: {before_pause}")
        window.pause_recording()
        paused = window._controller.snapshot()

        commanded: dict[str, float] = {}
        for name in window.config.logical_joint_names:
            lower, upper = window._report.limits_degrees[name]
            current = initial[name]
            commanded[name] = current + 0.25 if current + 0.25 <= upper else current - 0.25
            window._target_models[name].set_value(commanded[name])
            window._speed_models[name].set_value(5.0)
        window.move_all()
        for _ in range(240):
            simulation_app.update()
            if window._controller.snapshot().state is MotionState.REACHED:
                break
        moved = window._controller.snapshot()
        if moved.state is not MotionState.REACHED:
            raise RuntimeError(f"GUI motion did not reach its targets: {moved}")
        if any(
            abs(moved.current_degrees[name] - commanded[name]) > 0.05
            for name in window.config.logical_joint_names
        ):
            raise AssertionError(
                f"GUI read-back differs from target: target={commanded}, "
                f"actual={dict(moved.current_degrees)}"
            )
        if (
            moved.recording_state is not RecordingState.PAUSED
            or moved.recorded_samples != paused.recorded_samples
            or moved.recording_elapsed_seconds != paused.recording_elapsed_seconds
        ):
            raise AssertionError(
                "Paused recording advanced while the articulation moved: "
                f"paused={paused}, moved={moved}"
            )

        window.resume_recording()
        for _ in range(3):
            simulation_app.update()
        resumed = window._controller.snapshot()
        if (
            resumed.recording_state is not RecordingState.RECORDING
            or resumed.recorded_samples <= paused.recorded_samples
        ):
            raise AssertionError(f"Recording did not resume correctly: {resumed}")
        window.stop_recording()
        if not recording_output.is_file():
            raise AssertionError(f"Recording output was not published: {recording_output}")
        with recording_output.open(encoding="utf-8", newline="") as stream:
            recorded_rows = list(csv.DictReader(stream))
        if not recorded_rows:
            raise AssertionError("Published recording contains no samples")
        last_row = recorded_rows[-1]
        if any(
            abs(float(last_row[name]) - moved.current_degrees[name]) > 0.05
            for name in window.config.logical_joint_names
        ):
            raise AssertionError(
                "First resumed segment did not preserve actual joint positions: "
                f"recorded={last_row}, actual={dict(moved.current_degrees)}"
            )
        metadata = json.loads(
            recording_output.with_name("pause_resume.metadata.json").read_text(
                encoding="utf-8"
            )
        )
        if metadata.get("recording_time_policy") != "exclude_paused_intervals":
            raise AssertionError(f"Unexpected recording time policy: {metadata}")
        if metadata.get("position_priority") != "actual_readback_no_interpolation":
            raise AssertionError(f"Unexpected position priority: {metadata}")

        for name, value in initial.items():
            window._target_models[name].set_value(value)
        window.move_all()
        for _ in range(240):
            simulation_app.update()
            if window._controller.snapshot().state is MotionState.REACHED:
                break
        restored = window._controller.snapshot()
        if restored.state is not MotionState.REACHED or any(
            abs(restored.current_degrees[name] - initial[name]) > 0.05
            for name in window.config.logical_joint_names
        ):
            raise AssertionError(
                f"GUI did not restore initial angles: initial={initial}, "
                f"actual={dict(restored.current_degrees)}"
            )
        window.shutdown()
        print(
            "PASS: GUI panel paused/resumed compressed-time recording, preserved actual "
            "angles, moved all joints, and restored them",
            flush=True,
        )
        return 0
    except BaseException:
        print("FAIL: GUI smoke test raised an exception", flush=True)
        traceback.print_exc()
        raise
    finally:
        if recording_temp is not None:
            recording_temp.cleanup()
        simulation_app.close()


if __name__ == "__main__":
    raise SystemExit(main())
