"""Isaac Sim Script Editor entrypoint for synchronized joint automation."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


AUTOMATION_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = AUTOMATION_ROOT / "automated_joint_sequence.json"

root_text = str(AUTOMATION_ROOT)
if root_text not in sys.path:
    sys.path.insert(0, root_text)

module_was_loaded = "synchronized_joint_automation" in sys.modules
import synchronized_joint_automation as automation_module  # noqa: E402


if module_was_loaded:
    old_window = automation_module._ACTIVE_WINDOW
    if old_window is not None:
        old_window.shutdown()
    automation_module = importlib.reload(automation_module)


automation_module.show_automation_window(CONFIG_PATH)
