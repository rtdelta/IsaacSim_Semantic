"""Safe argv-based detached process launch and identity checks."""

import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Mapping, Optional, Sequence


@dataclass
class ProcessHandle:
    process: subprocess.Popen
    token: str
    log_stream: IO[bytes]

    @property
    def pid(self) -> int:
        return int(self.process.pid)


class ProcessInspector:
    @staticmethod
    def token(pid: int) -> Optional[str]:
        if pid <= 0:
            return None
        if os.name != "nt":
            stat_path = Path(f"/proc/{pid}/stat")
            try:
                fields = stat_path.read_text(encoding="utf-8").split()
                return f"linux-start-ticks:{fields[21]}"
            except (FileNotFoundError, IndexError, OSError):
                return None
        # os.kill(pid, 0) terminates the target on Windows. Query the process
        # handle and creation timestamp instead so PID reuse is also detected.
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(
            process_query_limited_information, False, wintypes.DWORD(pid)
        )
        if not handle:
            return None
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return None
            if exit_code.value != still_active:
                return None
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel_time = wintypes.FILETIME()
            user_time = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel_time),
                ctypes.byref(user_time),
            ):
                return None
            ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
            return f"windows-creation-ticks:{ticks}"
        finally:
            kernel32.CloseHandle(handle)

    @classmethod
    def matches(cls, pid: Optional[int], token: Optional[str]) -> bool:
        if pid is None or token is None:
            return False
        return cls.token(pid) == token


class ProcessLauncher:
    def launch(
        self,
        argv: Sequence[str],
        *,
        log_path: Path,
        env: Optional[Mapping[str, str]] = None,
        cwd: Optional[Path] = None,
    ) -> ProcessHandle:
        if not argv or any(not isinstance(item, str) or not item for item in argv):
            raise ValueError("process argv must contain non-empty strings")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        stream = log_path.open("ab", buffering=0)
        try:
            process = subprocess.Popen(
                list(argv),
                cwd=None if cwd is None else str(cwd),
                env=None if env is None else dict(env),
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=subprocess.STDOUT,
                shell=False,
                start_new_session=True,
            )
            token = ProcessInspector.token(process.pid)
            if token is None:
                process.terminate()
                raise RuntimeError("could not determine child process identity")
            return ProcessHandle(process=process, token=token, log_stream=stream)
        except Exception:
            stream.close()
            raise

    @staticmethod
    def terminate(pid: int, token: str) -> bool:
        if not ProcessInspector.matches(pid, token):
            return False
        if os.name == "nt":
            os.kill(pid, signal.SIGTERM)
        else:
            os.killpg(pid, signal.SIGTERM)
        return True

    @staticmethod
    def kill(pid: int, token: str) -> bool:
        """Force-terminate a process only if its stable identity still matches."""

        if not ProcessInspector.matches(pid, token):
            return False
        if os.name == "nt":
            # Python maps SIGTERM to TerminateProcess on Windows.
            os.kill(pid, signal.SIGTERM)
        else:
            os.killpg(pid, signal.SIGKILL)
        return True
