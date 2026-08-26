from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path


class OutputLock:
    def __init__(self, output_root: Path) -> None:
        self._path = output_root / ".run.lock"
        self._acquired = False

    def __enter__(self) -> "OutputLock":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            descriptor = os.open(
                self._path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError as exc:
            raise RuntimeError(
                f"output is locked by another or interrupted run: {self._path}"
            ) from exc
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.write("\n")
        self._acquired = True
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._acquired:
            self._path.unlink(missing_ok=True)
            self._acquired = False

