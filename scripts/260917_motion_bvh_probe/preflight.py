"""Record environment and hash existing USDA files; never author source assets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def snapshot(roots):
    files = {}
    for root in roots:
        if not root.is_dir():
            continue
        for parent, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "__pycache__"}]
            for name in names:
                path = Path(parent) / name
                if path.suffix.lower() == ".usda" and path.is_file():
                    files[str(path)] = {"sha256": digest(path), "bytes": path.stat().st_size}
    return files


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--verify", action="store_true")
    a = p.parse_args()
    roots = [Path("/root/gpufree-data/IsaacSim_Asset"),
             Path("/root/gpufree-data/semantic/scripts/260907LidarVisualizer"),
             Path("/root/gpufree-data/semantic/scripts/260910NV3Lidar")]
    a.out.mkdir(parents=True, exist_ok=True)
    manifest = a.out / "source_usda_before.json"
    if a.verify:
        before = json.loads(manifest.read_text())
        changed, missing = [], []
        for name, old in before.items():
            path = Path(name)
            if not path.is_file():
                missing.append(name)
            elif digest(path) != old["sha256"]:
                changed.append(name)
        result = {"checked": len(before), "changed": changed, "missing": missing,
                  "unchanged": not changed and not missing}
        (a.out / "source_usda_verification.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
        return int(not result["unchanged"])
    if manifest.exists():
        raise RuntimeError("Refusing to replace the original before-experiment manifest")
    files = snapshot(roots)
    manifest.write_text(json.dumps(files, indent=2))
    env = {"time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "roots": list(map(str, roots)), "usda_count": len(files)}
    for name in ("VERSION", "kit/VERSION"):
        path = Path("/root/isaacsim") / name
        env[name] = path.read_text().strip() if path.exists() else None
    env["gpu"] = subprocess.check_output(["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.used", "--format=csv,noheader"], text=True).strip()
    env["candidate_scenes"] = [f for f in files if "combine" in Path(f).name.lower()]
    env["sensor_assets"] = [f for f in files if Path(f).name in {"MyNZ3.usda", "MyOS0.usda", "MyAiry.usda"}]
    env["extensions"] = [q.name for q in Path("/root/isaacsim/extscache").iterdir()
                         if q.name.startswith(("omni.sensors.nv.", "omni.hydra.rtx", "omni.usd.libs", "omni.usd.schema.omni_nurec", "omni.usd.schema.usd_particle"))]
    (a.out / "environment.json").write_text(json.dumps(env, indent=2))
    print(json.dumps(env, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
