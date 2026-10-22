"""Small SSH transport. Password is read only from the process environment."""
import argparse
import os
from pathlib import Path
import sys
import warnings
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

warnings.filterwarnings("ignore", message="Blowfish has been deprecated.*")
import paramiko


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["run", "put", "get"])
    p.add_argument("first")
    p.add_argument("second", nargs="?")
    p.add_argument("--timeout", type=float, default=45)
    a = p.parse_args()
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.load_host_keys(str(Path.home() / ".ssh/known_hosts"))
    client.connect("120.209.70.195", port=30162, username="root",
                   password=os.environ.pop("BVH_SSH_PASSWORD"),
                   look_for_keys=False, allow_agent=False, timeout=12)
    try:
        if a.action == "run":
            _, out, err = client.exec_command(a.first, timeout=a.timeout)
            # Commands used here produce bounded output; long jobs write remote logs.
            sys.stdout.write(out.read().decode("utf-8", errors="replace"))
            sys.stderr.write(err.read().decode("utf-8", errors="replace"))
            return out.channel.recv_exit_status()
        with client.open_sftp() as sftp:
            if a.action == "put":
                sftp.put(a.first, a.second)
            else:
                Path(a.second).parent.mkdir(parents=True, exist_ok=True)
                sftp.get(a.first, a.second)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
