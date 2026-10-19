"""Read-only remote probe; does not import project or third-party modules."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

root = Path("/root/gpufree-data")
print(json.dumps({
    "time_utc": datetime.now(timezone.utc).isoformat(),
    "hostname": os.uname().nodename,
    "cwd": os.getcwd(),
    "data_directory_exists": root.is_dir(),
    "semantic_scripts_exists": (root / "semantic/scripts").is_dir(),
}, ensure_ascii=False))
