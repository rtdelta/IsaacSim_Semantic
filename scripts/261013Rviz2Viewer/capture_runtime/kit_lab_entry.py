"""Task-owned entry wrapper; original preserved in backups/source snapshot."""
import runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).resolve().parent.parent/"kit_capture_entry.py"))
