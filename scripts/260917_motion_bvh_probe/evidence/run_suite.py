"""Run named cases serially so only one diagnostic app uses the GPU."""
import json
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parent
suite = json.loads(Path(sys.argv[1]).read_text())
for name, args in suite:
    print(time.time(), "START", name, flush=True)
    subprocess.run([sys.executable, str(root / "run_case.py"), name, *args], check=True)
    print(time.time(), "END", name, flush=True)
