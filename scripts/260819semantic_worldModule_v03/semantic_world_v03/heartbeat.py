"""Atomic worker heartbeat used by the external supervisor."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class HeartbeatWriter:
    def __init__(self, path: str | Path, *, run_id: str, worker_id: str) -> None:
        self.path = Path(path)
        self.run_id = run_id
        self.worker_id = worker_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last: dict[str, Any] = {}

    def touch(self, phase: str, **fields: Any) -> dict[str, Any]:
        payload = {
            "run_id": self.run_id,
            "worker_id": self.worker_id,
            "pid": os.getpid(),
            "phase": phase,
            "updated_unix": time.time(),
            **fields,
        }
        temporary = self.path.with_suffix(self.path.suffix + f".{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        os.replace(temporary, self.path)
        self._last = payload
        return payload

    @property
    def last(self) -> dict[str, Any]:
        return dict(self._last)


def read_heartbeat(path: str | Path) -> dict[str, Any] | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def phase_timeout(phase: str, *, startup: float, render: float, shutdown: float) -> float:
    if phase in {"starting", "loading_stage", "initializing_sensors", "warming"}:
        return startup
    if phase in {"closing", "complete"}:
        return shutdown
    return render

