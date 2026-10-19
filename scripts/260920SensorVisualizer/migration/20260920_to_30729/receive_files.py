"""Pull approved data from the old server; credentials arrive on stdin only."""
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import stat
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent

def hash_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def destination(root, rel):
    path = PurePosixPath(rel)
    if path.is_absolute() or not path.parts or any(p in {"", ".", ".."} for p in rel.split("/")):
        raise ValueError("Invalid destination path")
    if root.is_symlink():
        raise ValueError("Destination root is a symlink")
    dest = root
    for part in path.parts[:-1]:
        dest /= part
        if dest.is_symlink():
            raise ValueError("Destination parent is a symlink")
        dest.mkdir(exist_ok=True)
    dest /= path.name
    if dest.is_symlink():
        raise ValueError("Destination is a symlink")
    return dest

def main():
    credentials = json.loads(sys.stdin.buffer.readline())
    plan = json.loads((HERE / "selection.json").read_bytes())
    root = Path(plan["destination_root"])
    if str(root) != "/root/gpufree-data" or not root.is_dir():
        raise ValueError("Unexpected destination")
    expected = {r["path"]: r for r in plan["files"]}
    verified = {}
    result_path = HERE / "verified.jsonl"
    if result_path.exists():
        for line in result_path.read_text().splitlines():
            row = json.loads(line)
            if row["path"] in expected:
                p = destination(root, row["path"])
                if p.is_file() and p.stat().st_size == row["size"] and hash_file(p) == row["sha256"]:
                    verified[row["path"]] = row
    request = dict(plan, files=[r for r in plan["files"] if r["path"] not in verified])
    completed_bytes = sum(r["size"] for r in verified.values())
    errors = []
    start = time.time()
    current = None
    received = 0
    last_status = 0
    state = "running"

    def status(force=False):
        nonlocal last_status
        now = time.time()
        if force or now - last_status >= 5:
            row = dict(state=state, pid=os.getpid(), started_at=start, updated_at=now,
                       total_files=len(expected), total_bytes=sum(r["size"] for r in expected.values()),
                       verified_files=len(verified), verified_bytes=completed_bytes,
                       current_file=current["row"]["path"] if current else None,
                       current_bytes=received, elapsed_seconds=round(now-start, 2), errors=errors)
            tmp = HERE / "status.json.tmp"
            tmp.write_text(json.dumps(row, ensure_ascii=True, indent=2))
            tmp.replace(HERE / "status.json")
            last_status = now

    askpass = HERE / "askpass.py"
    env = os.environ.copy()
    env.update(SSH_ASKPASS=str(askpass), SSH_ASKPASS_REQUIRE="force", DISPLAY="migration:0",
               MIGRATION_SOURCE_PASSWORD=credentials.pop("password"))
    source_program = base64.b64encode((HERE / "export_source.py").read_bytes()).decode()
    remote_command = "python3 -I -S -B -c " + shlex.quote("import base64;exec(compile(base64.b64decode('" + source_program + "'),'<migration-export>','exec'))")
    args = ["ssh", "-T", "-p", str(credentials["port"]), "-o", "StrictHostKeyChecking=yes",
            "-o", "UserKnownHostsFile=" + str(HERE / "source_known_hosts"),
            "-o", "GlobalKnownHostsFile=/dev/null", "-o", "PreferredAuthentications=password",
            "-o", "PubkeyAuthentication=no", "-o", "NumberOfPasswordPrompts=1",
            "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4",
            "-o", "HostKeyAlias=[120.209.70.195]:30162",
            "root@" + credentials["host"], remote_command]
    status(True)
    stderr = open(HERE / "source_ssh.log", "ab", buffering=0)
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
                               env=env, start_new_session=True)
    del env["MIGRATION_SOURCE_PASSWORD"]
    final_marker = None
    try:
        process.stdin.write(base64.b64encode(json.dumps(request, ensure_ascii=True).encode()) + b"\n")
        process.stdin.close()
        with result_path.open("a", buffering=1) as log:
            while True:
                line = process.stdout.readline(2 * 1024 * 1024)
                if not line:
                    break
                if not line.endswith(b"\n"):
                    raise ValueError("Oversize or truncated protocol frame")
                kind, payload = line.rstrip(b"\n").split(b" ", 1)
                data = base64.b64decode(payload, validate=True)
                if kind == b"D":
                    if current is None:
                        raise ValueError("Data without a file header")
                    received += len(data)
                    if received > current["row"]["size"]:
                        raise ValueError("Received excess file bytes")
                    current["stream"].write(data)
                    current["hash"].update(data)
                    status()
                    continue
                row = json.loads(data)
                if kind == b"H":
                    if current is not None or row != expected.get(row["path"]):
                        raise ValueError("Unexpected file header")
                    dest = destination(root, row["path"])
                    if dest.exists():
                        raise FileExistsError("Unverified destination exists: " + row["path"])
                    partial = dest.with_name(dest.name + ".migration-partial")
                    fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
                    current = dict(row=row, dest=dest, partial=partial, stream=os.fdopen(fd,"wb"), hash=hashlib.sha256())
                    received = 0
                elif kind == b"E":
                    if current is None or row["path"] != current["row"]["path"] or received != row["size"] or current["hash"].hexdigest() != row["sha256"]:
                        raise ValueError("Source/received checksum or length mismatch")
                    current["stream"].flush()
                    os.fsync(current["stream"].fileno())
                    current["stream"].close()
                    if hash_file(current["partial"]) != row["sha256"]:
                        raise ValueError("Disk read-back checksum mismatch")
                    os.chmod(current["partial"], current["row"]["mode"] & 0o777)
                    os.utime(current["partial"], ns=(current["row"]["mtime_ns"], current["row"]["mtime_ns"]))
                    os.replace(current["partial"], current["dest"])
                    row.update(verified_at=time.time(), disk_readback_verified=True)
                    log.write(json.dumps(row, ensure_ascii=True) + "\n")
                    verified[row["path"]] = row
                    completed_bytes += row["size"]
                    current = None
                    received = 0
                elif kind == b"X":
                    errors.append(row)
                    if current is not None:
                        current["stream"].close()
                        current = None
                        received = 0
                elif kind == b"Z":
                    final_marker = row
                else:
                    raise ValueError("Unknown protocol frame")
                status()
        rc = process.wait(timeout=60)
        if rc or errors or current is not None or not final_marker or final_marker["errors"] or len(verified) != len(expected):
            raise RuntimeError("Transfer incomplete: exit=%s, verified=%s/%s" % (rc,len(verified),len(expected)))
        state = "complete"
    except Exception as exc:
        errors.append({"error": str(exc)})
        state = "failed"
        if current is not None:
            current["stream"].close()
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
        raise
    finally:
        stderr.close()
        status(True)

if __name__ == "__main__":
    main()
