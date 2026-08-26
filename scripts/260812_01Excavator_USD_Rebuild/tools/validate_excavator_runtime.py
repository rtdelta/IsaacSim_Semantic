#!/usr/bin/env python3
"""Load the generated excavator in Isaac Sim and validate its PhysX articulation."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usd", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    usd_path = args.usd.expanduser().resolve()
    report_path = args.report.expanduser().resolve()
    if not usd_path.is_file():
        parser.error(f"USD does not exist: {usd_path}")
    sys.argv = [sys.argv[0]]

    from isaacsim import SimulationApp

    app = SimulationApp({"headless": args.headless, "sync_loads": True})
    report = {
        "schema_version": "1.0",
        "kind": "excavator_runtime_validation_report",
        "usd": str(usd_path),
        "status": "failed",
    }
    try:
        import numpy as np
        import omni.timeline
        import omni.usd
        from isaacsim.core.prims import Articulation
        from pxr import UsdPhysics

        context = omni.usd.get_context()
        if not context.open_stage(str(usd_path)):
            raise RuntimeError(f"failed to open USD: {usd_path}")
        for _ in range(120):
            app.update()
            if context.get_stage() is not None:
                break
        stage = context.get_stage()
        if stage is None:
            raise RuntimeError("Stage did not become available")
        physics_scenes = [
            prim for prim in stage.Traverse() if prim.IsA(UsdPhysics.Scene)
        ]
        if not physics_scenes:
            UsdPhysics.Scene.Define(stage, "/RuntimeValidationPhysicsScene")
        root_path = "/Excavator/Links/track"
        root_prim = stage.GetPrimAtPath(root_path)
        if not root_prim or not root_prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            raise RuntimeError(f"ArticulationRootAPI not found at {root_path}")

        articulation = Articulation(root_path)
        timeline = omni.timeline.get_timeline_interface()
        timeline.play()
        timeline.commit()
        for _ in range(360):
            app.update()
            try:
                articulation.initialize()
                if articulation.is_physics_handle_valid():
                    break
            except Exception:
                continue
        if not articulation.is_physics_handle_valid():
            raise RuntimeError("articulation physics handle did not initialize")

        dof_names = list(articulation.dof_names)
        positions = np.asarray(articulation.get_joint_positions(), dtype=np.float64)
        if len(dof_names) != 4 or positions.shape != (4,):
            raise RuntimeError(
                f"expected four articulation DOFs, got names={dof_names}, positions={positions.shape}"
            )
        expected_names = [
            "track_cab_joint",
            "cab_boom_joint",
            "boom_arm_joint",
            "arm_bucket_joint",
        ]
        if set(dof_names) != set(expected_names):
            raise RuntimeError(f"unexpected DOF names: {dof_names}")
        if not np.isfinite(positions).all():
            raise RuntimeError(f"non-finite joint positions: {positions.tolist()}")

        root_pose_before = articulation.get_world_poses()
        target = positions.copy()
        target[0] += 0.01
        articulation.set_joint_positions(target)
        app.update()
        read_back = np.asarray(articulation.get_joint_positions(), dtype=np.float64)
        if abs(float(read_back[0] - target[0])) > 1.0e-4:
            raise RuntimeError(
                f"joint position write/read failed: target={target.tolist()}, actual={read_back.tolist()}"
            )
        articulation.set_joint_positions(positions)
        app.update()
        root_pose_after = articulation.get_world_poses()
        report.update(
            {
                "status": "passed",
                "articulation_root_path": root_path,
                "dof_count": len(dof_names),
                "dof_names": dof_names,
                "initial_joint_positions_rad": positions.tolist(),
                "position_write_read_passed": True,
                "floating_root_pose_readable": root_pose_before is not None and root_pose_after is not None,
            }
        )
        return_code = 0
    except BaseException as exc:
        report["error"] = repr(exc)
        report["traceback"] = traceback.format_exc()
        return_code = 1
    finally:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        app.close()
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
