"""Launch Isaac Sim GUI with the excavator action recorder panel."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_USD = Path("/root/gpufree-data/wyb/StageMaterial/usd_ply_combined_02.usda")
DEFAULT_CSV_DIR = PROJECT_DIR / "trajectories"


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usd", default=str(DEFAULT_USD), help="USD/USDA stage to open")
    parser.add_argument(
        "--csv-dir", default=str(DEFAULT_CSV_DIR), help="CSV output/input directory"
    )
    parser.add_argument(
        "--csv-name", default="excavator_manual_01.csv", help="CSV filename only"
    )
    parser.add_argument(
        "--record",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable recording controls; default is --no-record",
    )
    parser.add_argument(
        "--playback-mode", choices=("hold", "loop"), default="hold"
    )
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Automated-test option; normal recorder use is GUI mode",
    )
    return parser.parse_known_args()


def main() -> int:
    args, kit_args = parse_args()
    sys.argv = [sys.argv[0], *kit_args]

    from isaacsim import SimulationApp

    simulation_app = SimulationApp(
        launch_config={
            "headless": args.headless,
            "renderer": "RaytracedLighting",
            "sync_loads": True,
        }
    )
    panel = None
    try:
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

        from excavator_gui_recorder import RecorderGuiConfig, show_recorder_window

        panel = show_recorder_window(
            RecorderGuiConfig(
                csv_directory=Path(args.csv_dir),
                csv_filename=args.csv_name,
                recording_enabled=args.record,
                playback_mode=args.playback_mode,
            )
        )
        while simulation_app.is_running():
            simulation_app.update()
        return 0
    except Exception as exc:
        print(f"[run-gui] ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if panel is not None:
            panel.shutdown()
        simulation_app.close()


if __name__ == "__main__":
    raise SystemExit(main())

