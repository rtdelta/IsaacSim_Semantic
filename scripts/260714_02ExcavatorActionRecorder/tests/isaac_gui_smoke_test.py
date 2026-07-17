"""Remote Isaac Sim smoke test for stage binding, GUI creation, and CSV recording."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--usd",
        default="/root/gpufree-data/wyb/StageMaterial/usd_ply_combined_02.usda",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    from isaacsim import SimulationApp

    simulation_app = SimulationApp(
        launch_config={"headless": True, "renderer": "RaytracedLighting", "sync_loads": True}
    )
    panel = None
    try:
        import carb.settings
        import omni.timeline
        import omni.usd
        from isaacsim.core.experimental.utils.stage import is_stage_loading

        usd_path = Path(args.usd).expanduser().resolve()
        if not usd_path.is_file():
            raise FileNotFoundError(f"USD stage not found: {usd_path}")
        if not omni.usd.get_context().open_stage(str(usd_path)):
            raise RuntimeError(f"Failed to open USD stage: {usd_path}")
        simulation_app.update()
        simulation_app.update()
        while is_stage_loading():
            simulation_app.update()

        carb.settings.get_settings().set("/app/player/useFixedTimeStepping", True)
        timeline = omni.timeline.get_timeline_interface()
        timeline.set_time_codes_per_second(60.0)
        timeline.set_current_time(0.0)
        timeline.set_end_time(10.0)
        timeline.set_looping(False)
        timeline.commit()

        from excavator_gui_recorder import ExcavatorRecorderWindow, RecorderGuiConfig
        from trajectory import JointTrajectory

        with tempfile.TemporaryDirectory(prefix="excavator-recorder-smoke-") as temp_dir:
            csv_path = Path(temp_dir) / "remote_smoke.csv"
            panel = ExcavatorRecorderWindow(
                RecorderGuiConfig(
                    csv_directory=Path(temp_dir),
                    csv_filename=csv_path.name,
                    recording_enabled=True,
                    playback_mode="hold",
                )
            )
            description = panel.controller.describe()
            if len(description) != 4:
                raise AssertionError(f"Expected four joints, got {description}")
            print(f"[isaac-smoke] Bound joints: {[item['name'] for item in description]}")

            cab_lower, cab_upper = panel.controller.limits()["cab"]
            current_cab = panel.controller.read_targets()["cab"]
            test_cab = min(cab_upper, max(cab_lower, current_cab + 0.5))
            panel.set_manual_target("cab", test_cab)

            if not panel.start_recording():
                raise RuntimeError("GUI panel did not start recording")
            for _ in range(30):
                simulation_app.update()
            final_path = panel.stop_recording()
            if final_path is None or not final_path.is_file():
                raise AssertionError("Recorder did not publish the final CSV")

            trajectory = JointTrajectory.from_csv(final_path)
            if len(trajectory.keyframes) < 2:
                raise AssertionError("Remote recording has fewer than two samples")
            print(
                f"[isaac-smoke] Recorded {len(trajectory.keyframes)} samples, "
                f"duration={trajectory.duration:.9f}s"
            )

            loaded = panel.load_trajectory()
            if loaded is None:
                raise AssertionError("GUI panel could not reload its recorded CSV")
            if not panel.play_trajectory():
                raise AssertionError("GUI panel could not start CSV playback")
            for _ in range(5):
                simulation_app.update()
            panel.stop_playback()

        print("[isaac-smoke] PASS")
        return 0
    finally:
        if panel is not None:
            panel.shutdown()
        simulation_app.close()


if __name__ == "__main__":
    raise SystemExit(main())

