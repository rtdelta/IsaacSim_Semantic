"""Open this file in Isaac Sim Script Editor and press Run."""

import asyncio
import builtins
import importlib
from pathlib import Path
import sys

PROJECT_DIR = Path("/root/gpufree-data/semantic/scripts/260907LidarVisualizer")
# Supports execution as a file as well as pasting into Script Editor.
if "__file__" in globals() and Path(__file__).name == "run_in_isaac.py":
    PROJECT_DIR = Path(__file__).resolve().parent


async def _launch(project_dir, previous_launch):
    if previous_launch and not previous_launch.done():
        await previous_launch
    previous = getattr(builtins, "_lidar_visualizer_session", None) or getattr(builtins, "_lidar_visualizer_instance", None)
    instance_before = getattr(builtins, '_lidar_visualizer_instance', None)
    resume = bool(instance_before and instance_before.timeline.is_playing())
    if previous is not None:
        await previous.close()
    if str(project_dir) not in sys.path:
        sys.path.insert(0, str(project_dir))
    # Reload only after the previous instance has released its callbacks/resources.
    from lidar_visualizer import config, discovery, recording, runtime, motion_profile, sensor_pose, pose_panel, joint_control, joint_panel, simulation_pacing, cloud_rate, robot_discovery, state_publication, render_lease, session, reference_frames, frame_overlay
    for module in (reference_frames, frame_overlay, motion_profile, joint_control, simulation_pacing, cloud_rate, config, discovery, recording, sensor_pose, pose_panel, joint_panel, robot_discovery, state_publication, render_lease, runtime, session):
        importlib.reload(module)
    if "lidar_visualizer.articulation_motion" in sys.modules:
        importlib.reload(sys.modules["lidar_visualizer.articulation_motion"])
    manager = session.SceneSession(project_dir)
    builtins._lidar_visualizer_session = manager
    try:
        await manager.refresh()
        if resume and manager.instance:
            manager.instance.timeline.play()
    except Exception:
        await manager.close()
        raise


def _report(task):
    if not task.cancelled() and task.exception():
        import traceback
        traceback.print_exception(task.exception())


_previous_launch = getattr(builtins, "_lidar_visualizer_launch", None)
_task = asyncio.ensure_future(_launch(PROJECT_DIR, _previous_launch))
builtins._lidar_visualizer_launch = _task
_task.add_done_callback(_report)
