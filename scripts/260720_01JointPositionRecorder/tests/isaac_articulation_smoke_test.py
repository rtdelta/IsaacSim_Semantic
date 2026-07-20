"""Runtime smoke test to execute with Isaac Sim's Python launcher.

Example:
    ./python.sh tests/isaac_articulation_smoke_test.py \
        --usd /root/gpufree-data/wyb/StageMaterial02/Sim_Fangshan_07.usda
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--usd", required=True)
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--offset-degrees", type=float, default=0.25)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    from isaacsim import SimulationApp

    simulation_app = SimulationApp({"headless": args.headless})
    try:
        project_root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(project_root / "src"))

        import omni.timeline
        import omni.usd

        from joint_position_recorder import (
            IsaacArticulationAdapter,
            load_project_config,
            validate_stage,
        )

        profile = load_project_config(
            project_root / "profiles" / "excavator_four_joint_default.json"
        )
        context = omni.usd.get_context()
        if not context.open_stage(str(Path(args.usd).expanduser().resolve())):
            raise RuntimeError(f"Failed to open USD: {args.usd}")
        for _ in range(10):
            simulation_app.update()

        report = validate_stage(context.get_stage(), profile).require_valid()
        adapter = IsaacArticulationAdapter(
            report.articulation_root_path,
            tuple(report.dof_names[name] for name in profile.logical_joint_names),
        )
        adapter.bind()
        timeline = omni.timeline.get_timeline_interface()
        timeline.play()
        timeline.commit()
        for _ in range(240):
            simulation_app.update()
            if adapter.ready:
                break
        if not adapter.ready:
            raise RuntimeError("Articulation tensor did not initialize within 240 updates")

        adapter.validate_runtime()
        initial = adapter.get_positions_degrees()
        commanded: list[float] = []
        for name, value in zip(profile.logical_joint_names, initial):
            lower, upper = report.limits_degrees[name]
            commanded.append(min(upper, max(lower, value + args.offset_degrees)))

        adapter.set_positions_degrees(commanded)
        simulation_app.update()
        read_back = adapter.get_positions_degrees()
        if any(abs(actual - expected) > 0.05 for actual, expected in zip(read_back, commanded)):
            raise AssertionError(
                f"Position read-back differs from command: command={commanded}, actual={read_back}"
            )

        adapter.set_positions_degrees(initial)
        simulation_app.update()
        print(
            "PASS: validated 4-DOF articulation, wrote and restored joint positions",
            flush=True,
        )
        print(f"root={report.articulation_root_path}", flush=True)
        print(f"dofs={report.dof_names}", flush=True)
        return 0
    except BaseException:
        print("FAIL: articulation smoke test raised an exception", flush=True)
        traceback.print_exc()
        raise
    finally:
        simulation_app.close()


if __name__ == "__main__":
    raise SystemExit(main())
