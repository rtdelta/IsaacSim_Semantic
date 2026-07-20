"""Create the real recorder window and verify automatic stage binding."""

from __future__ import annotations

import argparse
import runpy
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
            "PASS: GUI panel bound, moved all four joints at configured speed, and restored them",
            flush=True,
        )
        return 0
    except BaseException:
        print("FAIL: GUI smoke test raised an exception", flush=True)
        traceback.print_exc()
        raise
    finally:
        simulation_app.close()


if __name__ == "__main__":
    raise SystemExit(main())
