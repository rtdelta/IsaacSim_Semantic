"""Cross-platform advisory GPU lock used by the headless worker."""

import os
from pathlib import Path
from typing import Optional


class GpuLock:
    def __init__(self, path: Path, blocking: bool = False) -> None:
        self.path = Path(path)
        self.blocking = blocking
        self._stream = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                mode = msvcrt.LK_LOCK if self.blocking else msvcrt.LK_NBLCK
                stream.seek(0)
                if stream.tell() == 0 and self.path.stat().st_size == 0:
                    stream.write(b"0")
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), mode, 1)
            else:
                import fcntl

                operation = fcntl.LOCK_EX
                if not self.blocking:
                    operation |= fcntl.LOCK_NB
                fcntl.flock(stream.fileno(), operation)
            stream.seek(0)
            stream.truncate()
            stream.write(f"pid={os.getpid()}\n".encode("ascii"))
            stream.flush()
            os.fsync(stream.fileno())
        except Exception:
            stream.close()
            raise
        self._stream = stream

    def release(self) -> None:
        if self._stream is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._stream.seek(0)
                msvcrt.locking(self._stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
        finally:
            self._stream.close()
            self._stream = None

    def __enter__(self) -> "GpuLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.release()

