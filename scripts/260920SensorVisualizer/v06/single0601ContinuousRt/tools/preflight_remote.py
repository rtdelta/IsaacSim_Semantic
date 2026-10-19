"""Scoped read-only inventory; executed through the pinned SSH wrapper."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import time


def file_record(path):
    p = Path(path)
    if not p.is_file():
        return {"path": str(p), "exists": False}
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return {"path": str(p), "exists": True, "size_bytes": p.stat().st_size,
            "sha256": h.hexdigest()}


def command(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=20)
    return {"exit_code": p.returncode, "stdout": p.stdout[:12000], "stderr": p.stderr[:1500]}


root = Path("/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06")
install = Path("/root/isaacsim")
processes = []
for p in Path("/proc").iterdir():
    if not p.name.isdigit():
        continue
    try:
        parts = (p / "cmdline").read_bytes().split(b"\0")
        if any(b"/kit/kit" in x for x in parts):
            processes.append({"pid": int(p.name), "program": "isaac-kit",
                              "project_owned": any(b"single0601ContinuousRt" in x for x in parts)})
    except (OSError, PermissionError):
        pass
source_files = [file_record(p) for p in sorted(root.rglob("*"))
                if p.is_file() and p.suffix in (".py", ".json", ".kit", ".sh")
                and not any(x in p.parts for x in ("single0601ContinuousRt", "reports", "__pycache__"))]
versions = []
for pattern in ("VERSION*", "kit/VERSION*", "extscache/omni.replicator.core-*/config/extension.toml",
                "extscache/omni.sensors.nv.common-*/config/extension.toml",
                "exts/isaacsim.core.simulation_manager/config/extension.toml"):
    for p in install.glob(pattern):
        text = p.read_text(errors="replace")
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        versions.append({"path": str(p), "version": match.group(1) if match else text.strip()[:120]})
scene = "/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda"
result = {"schema_version": 1, "hostname": platform.node(), "os": platform.platform(),
          "python": platform.python_version(), "monotonic_ns": str(time.monotonic_ns()),
          "scene": file_record(scene), "source_files": source_files, "installed_metadata": versions,
          "gpu": command(["nvidia-smi", "--query-gpu=uuid,name,driver_version,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"]),
          "isaac_processes": processes, "gui_display_20_available": Path("/tmp/.X11-unix/X20").exists(),
          "cpu_max": Path("/sys/fs/cgroup/cpu.max").read_text().strip(),
          "memory_max": Path("/sys/fs/cgroup/memory.max").read_text().strip(),
          "ros": command(["/bin/bash", "-c", "source /opt/ros/jazzy/setup.bash && python3 -I -c 'import rosbag2_py, rclpy; print(rosbag2_py.get_registered_writers())'"])}
print(json.dumps(result, ensure_ascii=False))
