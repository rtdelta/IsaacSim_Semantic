"""Read-only instance comparison. Run on stdin; writes no remote files.

Direct Linux x86_64 read/getdents syscalls bypass the source's confirmed hooks.
This does not neutralize the already-loaded preload library or its constructors.
Only a base64-encoded JSON result is emitted, so source pipe filtering cannot
remove literal path/address patterns from the evidence transport.
"""
import base64
import ctypes
import datetime
import hashlib
import json
import marshal
import mmap
import os
import re
import stat
import struct
import time
import zlib

LIBC = ctypes.CDLL("libc.so.6", use_errno=True)
LIBC.syscall.restype = ctypes.c_long

def rawread(path, limit=24000000):
    fd = os.open(path, os.O_RDONLY)
    try:
        out = []
        total = 0
        buf = ctypes.create_string_buffer(65536)
        while True:
            n = LIBC.syscall(0, fd, buf, len(buf))
            if n < 0:
                raise OSError(ctypes.get_errno(), "read syscall", path)
            if n == 0:
                return b"".join(out)
            total += n
            if total > limit:
                raise ValueError("read limit: " + path)
            out.append(buf.raw[:n])
    finally:
        os.close(fd)

def rawlist(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        result = []
        buf = ctypes.create_string_buffer(65536)
        while True:
            n = LIBC.syscall(217, fd, buf, len(buf))
            if n < 0:
                raise OSError(ctypes.get_errno(), "getdents64", path)
            if n == 0:
                return result
            data = buf.raw[:n]
            offset = 0
            while offset < n:
                size = struct.unpack_from("H", data, offset + 16)[0]
                if size < 19:
                    raise ValueError("invalid directory entry")
                name = data[offset+19:offset+size].split(b"\0",1)[0].decode(errors="replace")
                if name not in (".", ".."):
                    result.append(name)
                offset += size
    finally:
        os.close(fd)

def text(path, default=""):
    try:
        return rawread(path).decode(errors="replace")
    except (OSError, ValueError):
        return default

def metadata(path):
    try:
        s = os.lstat(path)
        r = dict(mode=oct(stat.S_IMODE(s.st_mode)), size=s.st_size,
                 mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns)
        if stat.S_ISLNK(s.st_mode):
            r.update(kind="link", target=os.readlink(path))
        elif stat.S_ISDIR(s.st_mode):
            r["kind"] = "dir"
        elif stat.S_ISREG(s.st_mode):
            r["kind"] = "file"
            fd = os.open(path, os.O_RDONLY)
            try:
                if s.st_size:
                    with mmap.mmap(fd, 0, access=mmap.ACCESS_READ) as view:
                        r["sha256"] = hashlib.sha256(view).hexdigest()
                        r["md5"] = hashlib.md5(view).hexdigest()
                else:
                    r["sha256"] = hashlib.sha256(b"").hexdigest()
                    r["md5"] = hashlib.md5(b"").hexdigest()
            finally:
                os.close(fd)
        else:
            r["kind"] = "special"
        return r
    except (OSError, ValueError) as exc:
        return {"error": str(exc)}

def tree(root, skip_cache=False):
    result = {}
    def visit(path):
        try:
            names = sorted(rawlist(path))
        except OSError:
            return
        for name in names:
            if skip_cache and (name == "__pycache__" or name.endswith((".pyc", ".pyo"))):
                continue
            p = path + "/" + name
            try:
                s = os.lstat(p)
                if stat.S_ISDIR(s.st_mode):
                    visit(p)
                elif stat.S_ISREG(s.st_mode) or stat.S_ISLNK(s.st_mode):
                    result[p] = metadata(p)
            except OSError:
                pass
    visit(root)
    return result

def package_db():
    packages = {}
    for paragraph in text("/var/lib/dpkg/status").split("\n\n"):
        fields = {}
        for line in paragraph.splitlines():
            if line and not line[0].isspace() and ": " in line:
                k,v = line.split(": ",1)
                fields[k] = v
        if fields.get("Status") == "install ok installed":
            packages[fields["Package"]] = {k:fields.get(k) for k in ("Version","Architecture")}
    return packages

def process_snapshot():
    rows = {}
    for pid in rawlist("/proc"):
        if not pid.isdigit():
            continue
        try:
            path = "/proc/" + pid
            data = text(path + "/stat")
            end = data.rfind(")")
            fields = data[end+2:].split()
            if not fields:
                continue
            try:
                exe = os.readlink(path + "/exe")
            except OSError:
                exe = ""
            rows[pid] = dict(pid=int(pid), comm=text(path+"/comm").strip(),
                             ppid=int(fields[1]), state=fields[0],
                             ticks=int(fields[11])+int(fields[12]),
                             start_ticks=int(fields[19]), threads=int(fields[17]),
                             rss_bytes=int(fields[21])*os.sysconf("SC_PAGE_SIZE"), exe=exe)
        except (OSError, ValueError, IndexError):
            pass
    return rows

def safe_lines(path, limit=30):
    result = []
    for line in text(path).splitlines():
        if re.search(r"password|token|secret|credential|authorization|cookie",line,re.I):
            result.append("[credential-related line omitted]")
        else:
            result.append(line[:2000])
    return result[-limit:]

def read_comparison(path):
    result = {}
    for method in ("raw", "normal"):
        try:
            if method == "raw":
                data = rawread(path)
            else:
                with open(path,"rb") as stream:
                    data = stream.read()
            r = dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
            if path.endswith(".pyc"):
                try:
                    # Deserialize only; NEVER execute the resulting code object.
                    obj = marshal.loads(data[16:])
                    r["marshal_result"] = type(obj).__name__
                except Exception as exc:
                    r["marshal_error"] = str(exc)
            result[method] = r
        except Exception as exc:
            result[method] = {"error":str(exc)}
    return result

def main():
    result = {"collected_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()}
    result["baseline"] = {
        "os_release":text("/etc/os-release"), "kernel":os.uname().release,
        "isaac_version":text("/root/isaacsim/VERSION").strip(),
        "uptime":text("/proc/uptime").strip(), "cpu_max":text("/sys/fs/cgroup/cpu.max").strip(),
        "memory_max":text("/sys/fs/cgroup/memory.max").strip(),
        "preload":text("/etc/ld.so.preload"),
        "self_loaded_preload_maps":[line for line in text("/proc/self/maps").splitlines()
                                     if any(n in line for n in (".libproc.so","libblock_nvidia","libnvenc_fix"))]
    }
    result["packages"] = package_db()
    selected = re.compile(r"^(xserver-xorg|xfce4|xfconf|libxfce4|x11-|xauth$|xinit$|dbus|libgtk|libgdk|libglib2|python3(?:\.12)?(?:-|$)|libpython3|libc6$|supervisor$|selkies)")
    infos = rawlist("/var/lib/dpkg/info")
    package_files = {}
    for package in result["packages"]:
        if not selected.search(package):
            continue
        names = [n for n in infos if n == package+".md5sums" or n.startswith(package+":") and n.endswith(".md5sums")]
        for name in names:
            for line in text("/var/lib/dpkg/info/"+name).splitlines():
                pieces = line.split(None,1)
                if len(pieces) != 2:
                    continue
                expected, rel = pieces
                if rel.startswith(("usr/share/doc/","usr/share/man/","usr/share/locale/")):
                    continue
                p = "/"+rel
                row = metadata(p)
                row.update(package=package, expected_md5=expected)
                package_files[p] = row
    result["package_files"] = package_files
    result["desktop_venv"] = tree("/etc/.gpufree/venv",skip_cache=True)
    result["config_files"] = {}
    for root in ("/etc/supervisor","/etc/cron.d","/etc/cron.daily","/etc/systemd/system",
                 "/etc/xdg/autostart","/root/.config/autostart","/root/.config/xfce4"):
        result["config_files"].update(tree(root))
    for path in ("/etc/gpufree","/etc/ld.so.preload","/usr/lib/.libproc.so",
                 "/usr/lib/libblock_nvidia.so","/usr/lib/libnvenc_fix.so",
                 "/var/lib/.dpkg-triggers-2890","/etc/crontab","/etc/rc.local",
                 "/etc/supervisord.conf","/etc/profile","/root/.bashrc","/root/.profile",
                 "/etc/ssh/sshd_config","/root/.vnc/xstartup"):
        result["config_files"][path] = metadata(path)
    result["startup_text"] = {}
    for p in result["config_files"]:
        if (p.startswith("/etc/supervisor/") or p.startswith("/etc/cron.") or p in ("/etc/crontab","/etc/rc.local","/etc/supervisord.conf")) and result["config_files"][p].get("kind") == "file":
            result["startup_text"][p] = safe_lines(p,250)
    first = process_snapshot()
    t0 = time.monotonic()
    time.sleep(1)
    second = process_snapshot()
    dt = time.monotonic()-t0
    hz = os.sysconf("SC_CLK_TCK")
    for pid,row in second.items():
        prev = first.get(pid)
        row["cpu_cores_sample"] = round((row["ticks"]-prev["ticks"])/hz/dt,3) if prev and row["start_ticks"] == prev["start_ticks"] else None
    result["processes"] = list(second.values())
    result["visible_proc_pids"] = [int(p) for p in os.listdir("/proc") if p.isdigit()]
    result["tcp_listeners"] = []
    for path in ("/proc/net/tcp","/proc/net/tcp6"):
        for line in text(path).splitlines()[1:]:
            f = line.split()
            if len(f)>9 and f[3] == "0A":
                result["tcp_listeners"].append({"source":path,"local_hex":f[1],"port":int(f[1].split(":")[1],16),"inode":f[9]})
    result["read_comparisons"] = {}
    for p in ("/etc/ld.so.preload",
              "/usr/lib/python3/dist-packages/psutil/_pslinux.py",
              "/usr/lib/python3/dist-packages/psutil/__pycache__/_pslinux.cpython-312.pyc",
              "/etc/.gpufree/venv/lib/python3.12/site-packages/psutil/_pslinux.py",
              "/etc/.gpufree/venv/lib/python3.12/site-packages/psutil/__pycache__/_pslinux.cpython-312.pyc"):
        result["read_comparisons"][p] = read_comparison(p)
    result["log_tails"] = {p:safe_lines(p,55) for p in ("/var/log/selkies.log","/tmp/.desktop.log","/var/log/xorg.log","/var/log/supervisor/supervisord.log")}
    result["memory_events"] = text("/sys/fs/cgroup/memory.events")
    result["memory_current"] = text("/sys/fs/cgroup/memory.current")
    wire = base64.b64encode(zlib.compress(json.dumps(result,ensure_ascii=True).encode())).decode()
    print("AUDITZ64:"+wire)

if __name__ == "__main__":
    main()
