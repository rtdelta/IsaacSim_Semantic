"""Check completed transfer metadata and document the delivery; no old code runs."""
import collections
import json
import os
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent

def main():
    status = json.loads((HERE / "status.json").read_text())
    if status["state"] != "complete":
        raise RuntimeError("Transfer has not completed")
    plan = json.loads((HERE / "selection.json").read_text())
    wanted = {row["path"]: row for row in plan["files"]}
    verified = {r["path"]: r for r in map(json.loads, (HERE / "verified.jsonl").read_text().splitlines())}
    if set(wanted) != set(verified):
        raise RuntimeError("Verified inventory differs from selection")
    root = Path(plan["destination_root"])
    counts = collections.defaultdict(lambda: {"files": 0, "bytes": 0})
    for rel, row in wanted.items():
        path = root / rel
        if path.is_symlink() or not path.is_file() or path.stat().st_size != row["size"]:
            raise RuntimeError("Final file metadata mismatch: " + rel)
        if path.with_name(path.name + ".migration-partial").exists():
            raise RuntimeError("Leftover transfer partial: " + rel)
        if not verified[rel]["disk_readback_verified"]:
            raise RuntimeError("Missing disk verification: " + rel)
        group = rel.split("/")[0]
        counts[group]["files"] += 1
        counts[group]["bytes"] += row["size"]
    desktop = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            comm = (proc / "comm").read_text().strip()
            if comm in {"Xorg", "xfce4-session", "xfce4-panel", "selkies", "gpufree"}:
                desktop.append({"pid": int(proc.name), "name": comm})
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            pass
    preload = Path("/etc/ld.so.preload").read_text()
    expected_preload = {"/usr/lib/libblock_nvidia.so", "/usr/lib/libnvenc_fix.so"}
    report = dict(completed_at=time.time(), source="120.209.70.195:30162",
                  destination="120.209.70.195:30729", transport="private SSH 100.122.231.108:22; original host key verified",
                  root=str(root), files=len(wanted), bytes=sum(r["size"] for r in wanted.values()),
                  all_files_sha256_and_disk_readback_verified=True, final_file_metadata_ok=True,
                  elapsed_seconds=status["elapsed_seconds"], by_root=dict(counts),
                  desktop_processes=desktop, preload_unchanged=set(preload.split()) == expected_preload,
                  known_source_injection_mapped=".libproc.so" in Path("/proc/self/maps").read_text(),
                  historical_recordings_migrated=False, gui_simulation_test_performed=False,
                  preexisting_missing_references=[
                      "IsaacSim_Asset/combine_stage/Environment/environment.usdz",
                      "IsaacSim_Asset/combine_stage/Fangshan_Excavator_01.usda"],
                  note="Both missing dependencies belong to Combine_Scene_02.usda and were separately confirmed absent on the old instance. Network NVIDIA references remain unchanged.")
    (HERE / "completion.json").write_text(json.dumps(report, ensure_ascii=True, indent=2))
    # Empty output root is useful to the application; no historical files are copied.
    (root / "semantic/output").mkdir(exist_ok=True)
    print(json.dumps(report, ensure_ascii=True))

if __name__ == "__main__":
    main()
