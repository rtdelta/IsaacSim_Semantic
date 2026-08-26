"""Durable GPU and progress telemetry for a long-running job."""

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def append_jsonl(path: Path, value: Dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)


def probe_gpu() -> Dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"available": False, "warning": "nvidia-smi was not found"}
    completed = subprocess.run(
        [
            executable,
            "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,driver_version",
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
    devices = []
    for line in completed.stdout.splitlines():
        values = [item.strip() for item in line.split(",")]
        if len(values) != 7:
            continue
        try:
            devices.append(
                {
                    "index": int(values[0]),
                    "name": values[1],
                    "utilization_gpu_percent": int(values[2]),
                    "memory_used_mb": int(values[3]),
                    "memory_total_mb": int(values[4]),
                    "temperature_c": int(values[5]),
                    "driver_version": values[6],
                }
            )
        except ValueError:
            continue
    return {"available": bool(devices), "devices": devices}


class TelemetryRecorder:
    def __init__(self, output_dir: Path, gpu_probe=probe_gpu) -> None:
        self.root = Path(output_dir) / "telemetry"
        self.gpu_probe = gpu_probe

    def sample_gpu(
        self, *, segment_id: Optional[str], worker_pid: Optional[int]
    ) -> Dict[str, Any]:
        result = self.gpu_probe()
        event = {
            "at_utc": utc_now(),
            "segment_id": segment_id,
            "worker_pid": worker_pid,
            **result,
        }
        append_jsonl(self.root / "gpu.jsonl", event)
        return event

    def progress(self, value: Dict[str, Any]) -> None:
        append_jsonl(self.root / "progress.jsonl", {"at_utc": utc_now(), **value})

    def segment_timing(self, value: Dict[str, Any]) -> None:
        append_jsonl(
            self.root / "segment_timing.jsonl", {"at_utc": utc_now(), **value}
        )
