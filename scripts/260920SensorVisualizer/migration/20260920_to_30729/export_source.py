"""Read-only x86_64 Linux exporter. Entire output is base64-framed.

Reads use the read syscall to bypass the confirmed source LD_PRELOAD read hook.
The SSH pipe must also carry base64 to avoid filtering binary/text payloads.
No code or file obtained from the source is executed on the destination.
"""
import base64
import ctypes
import hashlib
import json
import os
import stat
import sys

LIBC = ctypes.CDLL("libc.so.6", use_errno=True)
LIBC.syscall.restype = ctypes.c_long
CHUNK = 768 * 1024

def send(kind, value):
    data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=True).encode()
    wire = kind.encode() + b" " + base64.b64encode(data) + b"\n"
    view = memoryview(wire)
    while view:
        count = os.write(1, view)
        view = view[count:]

def safe_path(root, rel):
    parts = rel.split("/")
    if not rel or rel.startswith("/") or any(x in {"", ".", ".."} for x in parts):
        raise ValueError("Invalid relative path")
    path = root
    for part in parts:
        path = os.path.join(path, part)
        if stat.S_ISLNK(os.lstat(path).st_mode):
            raise ValueError("Source path became a symlink: " + rel)
    return path

def main():
    request = json.loads(base64.b64decode(sys.stdin.buffer.readline()))
    root = request["source_root"]
    if root != "/root/gpufree-data":
        raise ValueError("Unexpected source root")
    errors = 0
    for row in request["files"]:
        rel = row["path"]
        try:
            path = safe_path(root, rel)
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                before = os.fstat(fd)
                if not stat.S_ISREG(before.st_mode) or before.st_size != row["size"] or before.st_mtime_ns != row["mtime_ns"]:
                    raise ValueError("Source changed since inventory: " + rel)
                send("H", row)
                digest = hashlib.sha256()
                size = 0
                buf = ctypes.create_string_buffer(CHUNK)
                while True:
                    count = LIBC.syscall(0, fd, buf, CHUNK)
                    if count < 0:
                        raise OSError(ctypes.get_errno(), "read syscall", rel)
                    if not count:
                        break
                    data = buf.raw[:count]
                    digest.update(data)
                    size += count
                    send("D", data)
                after = os.fstat(fd)
                if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) or size != before.st_size:
                    raise ValueError("Source modified during transfer: " + rel)
                send("E", {"path": rel, "size": size, "sha256": digest.hexdigest()})
            finally:
                os.close(fd)
        except Exception as exc:
            errors += 1
            send("X", {"path": rel, "error": str(exc)})
    send("Z", {"files": len(request["files"]), "errors": errors})
    return int(errors != 0)

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        send("X", {"error": str(exc)})
        sys.exit(1)
