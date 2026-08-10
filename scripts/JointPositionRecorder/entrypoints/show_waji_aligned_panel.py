"""Isaac Sim entrypoint for aligned-excavator WASD+FG and four-joint control."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
PROFILE_PATH = (
    PROJECT_ROOT / "profiles" / "waji_aligned_four_joint_floating.json"
)

source_text = str(SOURCE_ROOT)
if source_text not in sys.path:
    sys.path.insert(0, source_text)

modules_were_loaded = "joint_position_recorder.gui" in sys.modules

import joint_position_recorder.articulation_adapter as articulation_adapter_module  # noqa: E402
import joint_position_recorder.config as config_module  # noqa: E402
import joint_position_recorder.controller as controller_module  # noqa: E402
import joint_position_recorder.gui as gui_module  # noqa: E402
import joint_position_recorder.motion_planner as motion_planner_module  # noqa: E402
import joint_position_recorder.root_motion as root_motion_module  # noqa: E402
import joint_position_recorder.stage_validator as stage_validator_module  # noqa: E402
import joint_position_recorder.trajectory_recorder as trajectory_recorder_module  # noqa: E402


if modules_were_loaded:
    old_window = gui_module._ACTIVE_WINDOW
    if old_window is not None:
        old_window.shutdown()
    for module in (
        articulation_adapter_module,
        config_module,
        motion_planner_module,
        root_motion_module,
        stage_validator_module,
        trajectory_recorder_module,
        controller_module,
        gui_module,
    ):
        importlib.reload(module)


config = config_module.load_project_config(PROFILE_PATH)
gui_module.show_recorder_window(config, PROJECT_ROOT)
