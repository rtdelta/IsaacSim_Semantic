"""Isaac Sim Script Editor entrypoint for the independent controller project."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
PROFILE_PATH = PROJECT_ROOT / "profiles" / "excavator_four_joint_default.json"

source_text = str(SOURCE_ROOT)
if source_text not in sys.path:
    sys.path.insert(0, source_text)

from joint_position_recorder import load_project_config, show_recorder_window  # noqa: E402


config = load_project_config(PROFILE_PATH)
show_recorder_window(config, PROJECT_ROOT)
