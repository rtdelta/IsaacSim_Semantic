"""Host checks performed before starting the heavy SimulationApp process."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .bootstrap import loaded_libpython


def _default_gpu_probe() -> Dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"available": False, "warning": "nvidia-smi was not found"}
    completed = subprocess.run(
        [
            executable,
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
        check=False,
    )
    if completed.returncode != 0:
        return {
            "available": False,
            "warning": completed.stderr.strip() or "nvidia-smi failed",
        }
    devices = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    return {"available": bool(devices), "devices": devices}


def check_host_preflight(
    output_dir: Path,
    *,
    minimum_free_bytes: int = 64 * 1024 * 1024,
    gpu_probe: Optional[Callable[[], Dict[str, Any]]] = None,
    require_isaac_abi: bool = True,
) -> Dict[str, Any]:
    """Validate output durability, free space, GPU visibility, and Python ABI."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(output_dir)
    if usage.free < minimum_free_bytes:
        raise RuntimeError(
            f"insufficient output disk space: {usage.free} bytes free; "
            f"at least {minimum_free_bytes} required"
        )
    fd, probe_name = tempfile.mkstemp(prefix=".v04-write-probe-", dir=str(output_dir))
    try:
        os.write(fd, b"semantic-world-v04\n")
        os.fsync(fd)
    finally:
        os.close(fd)
        os.unlink(probe_name)

    gpu = (gpu_probe or _default_gpu_probe)()
    if not gpu.get("available"):
        raise RuntimeError(f"no usable NVIDIA GPU reported: {gpu.get('warning', gpu)}")

    libpython = loaded_libpython()
    executable = str(Path(sys.executable).resolve())
    if (
        require_isaac_abi
        and "isaacsim" in executable.casefold()
        and "kit/python/lib" not in libpython
    ):
        raise RuntimeError(
            "Isaac Python is linked to an unexpected libpython; use the v04 "
            f"ABI-safe wrapper. Loaded: {libpython}"
        )
    return {
        "sys_executable": executable,
        "sys_version": sys.version,
        "libpython": libpython,
        "disk": {
            "output_dir": str(output_dir.resolve()),
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
        },
        "gpu": gpu,
    }
