from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping


class ErrorJournal:
    def __init__(self, output_root: Path) -> None:
        self.destination = output_root / "errors.jsonl"
        self.temporary = output_root / "errors.jsonl.tmp"
        self._handle = None
        self.count = 0

    def __enter__(self) -> "ErrorJournal":
        self.destination.unlink(missing_ok=True)
        self.temporary.unlink(missing_ok=True)
        self._handle = self.temporary.open("w", encoding="utf-8", newline="\n")
        return self

    def write(self, error: Mapping[str, object]) -> None:
        if self._handle is None:
            raise RuntimeError("error journal is not open")
        self._handle.write(json.dumps(error, ensure_ascii=False) + "\n")
        self._handle.flush()
        self.count += 1

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        if exc_type is not None:
            self.temporary.unlink(missing_ok=True)
        elif self.count:
            os.replace(self.temporary, self.destination)
        else:
            self.temporary.unlink(missing_ok=True)
