"""Launch one bounded, isolated process and retain its status even after a crash."""
import argparse
import json
import os
from pathlib import Path
import resource
import signal
import shutil
import subprocess
import sys
import time

p = argparse.ArgumentParser()
p.add_argument("name")
p.add_argument("--timeout", type=float, default=150)
p.add_argument("--script", default="probe_case.py")
a, rest = p.parse_known_args()
root = Path(__file__).resolve().parent
out = root / "cases" / a.name
out.mkdir(parents=True, exist_ok=False)
worker = root / a.script
assert worker.resolve().parent == root
shutil.copyfile(worker, out / "probe_case_snapshot.py")
env = os.environ.copy()
for key in ("PYTHONHOME", "PYTHONPATH", "LD_PRELOAD", "VIRTUAL_ENV", "CONDA_PREFIX"):
    env.pop(key, None)
env["ROS_DOMAIN_ID"] = "173"
install = Path("/root/isaacsim")
paths = [str(path) for pattern in ("omni.sensors.nv.common-*/bin/checker_lib/bin",
                                  "omni.sensors.nv.common-*/bin", "omni.sensors.nv.lidar-*/bin/model_plugins")
         for path in (install / "extscache").glob(pattern)]
paths += [str(install / s) for s in ("kit/python/lib", "kit", "kit/kernel/plugins", "kit/plugins/rtx")]
env["LD_LIBRARY_PATH"] = ":".join(paths)
soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE, (min(65536, hard), hard))
command = [str(install / "python.sh"), str(worker), "--out", str(out), *rest]
start = time.monotonic()
status = {"command": command, "started_at": time.time()}
with (out / "console.log").open("w") as log:
    child = subprocess.Popen(command, cwd=install, env=env, stdout=log,
                             stderr=subprocess.STDOUT, start_new_session=True)
    status["pid"] = child.pid
    (out / "process.json").write_text(json.dumps(status, indent=2))
    try:
        status["exit_code"] = child.wait(timeout=a.timeout)
        status["timed_out"] = False
    except subprocess.TimeoutExpired:
        status["timed_out"] = True
        # Only this newly created process group belongs to this runner.
        os.killpg(child.pid, signal.SIGTERM)
        try:
            child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
        status["exit_code"] = child.returncode
status["wall_seconds"] = time.monotonic() - start
status["finished_at"] = time.time()
(out / "process.json").write_text(json.dumps(status, indent=2))
print(json.dumps(status), flush=True)
