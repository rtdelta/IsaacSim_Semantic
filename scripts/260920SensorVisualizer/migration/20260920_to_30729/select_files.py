"""Select project sources and input assets, excluding captures and old runtimes."""
import collections
import json
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
CACHE_DIRS = {"__pycache__", ".pytest_cache", ".ipynb_checkpoints", ".venv", "shadercache", "nv_shadercache", "_deps", "runtime_seed", "debug_tools"}
SOURCE_EXT = {".py", ".sh", ".ps1", ".md", ".toml", ".yaml", ".yml", ".rviz", ".kit", ".json", ".usda", ".usd", ".usdc", ".ini", ".cfg", ".txt"}

def exclusion(row):
    p = PurePosixPath(row["path"])
    parts = p.parts
    if parts[0] == "alistgo":
        return "file service binaries/state; not project assets or sources"
    if parts[:2] == ("semantic", "output"):
        return "historical capture outputs"
    if any(x in CACHE_DIRS or x.startswith(".runtime") for x in parts):
        return "generated runtime, cache, or third-party environment"
    if p.suffix in {".pyc", ".pyo", ".log", ".mcap", ".db3"} or "logs" in parts:
        return "compiled cache, log, or recording"
    if row["kind"] == "link":
        return "old runtime symlink"
    if row["kind"] not in {"file", "dir"}:
        return "special file"
    if parts[0] == "diagnostics":
        if "runtime" in parts:
            return "diagnostic runtime copy"
        if p.suffix.lower() not in SOURCE_EXT and row["kind"] == "file":
            return "diagnostic output/binary; retain source and configuration only"
    if parts[0] == "260910NV3Lidar" and len(parts) > 1 and parts[1] in {"reference_acceptance", "reports"}:
        if p.suffix.lower() not in {".py", ".sh", ".md"}:
            return "sensor validation output"
    if parts[:3] == ("semantic", "scripts", "260907LidarVisualizer") and any(x in parts[3:] for x in ("results", "artifacts", ".validation_staging")):
        if p.suffix.lower() not in SOURCE_EXT and row["kind"] == "file":
            return "validation output; retain source, configuration and test stages"
    if parts[:3] == ("semantic", "scripts", "260919MyAiryLidar") and "reports" in parts[3:] and p.suffix.lower() not in SOURCE_EXT:
        return "MyAiry validation output"
    return None

def main():
    rows = json.loads((HERE / "source_inventory.json").read_bytes())
    selected, excluded = [], []
    for row in rows:
        reason = exclusion(row)
        if reason:
            excluded.append(dict(row, reason=reason))
        elif row["kind"] == "file":
            selected.append(row)
    # Empty generated directories are not needed; parents are created by the receiver.
    selected.sort(key=lambda r: (0 if r["path"].startswith("IsaacSim_Asset/") else 1, r["path"]))
    plan = {"source_root": "/root/gpufree-data", "destination_root": "/root/gpufree-data", "files": selected}
    (HERE / "selection.json").write_text(json.dumps(plan, ensure_ascii=True), encoding="utf-8")
    (HERE / "excluded.json").write_text(json.dumps(excluded, ensure_ascii=True), encoding="utf-8")
    totals = collections.defaultdict(lambda: {"files": 0, "bytes": 0})
    for row in selected:
        key = row["path"].split("/")[0]
        totals[key]["files"] += 1
        totals[key]["bytes"] += row["size"]
    summary = {"files": len(selected), "bytes": sum(x["size"] for x in selected), "by_root": dict(totals)}
    (HERE / "selection_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
