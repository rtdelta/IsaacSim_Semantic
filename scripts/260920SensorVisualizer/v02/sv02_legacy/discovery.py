"""Build a ROS-safe sensor list from loaded OmniLidar prims at startup."""

from collections import Counter
import hashlib
from pathlib import PurePosixPath
import re


def sensors_from_paths(paths, world_frame="world"):
    """Use the mount name for generic sensor leaves; resolve duplicate names by path."""
    paths = sorted(set(map(str, paths)))
    bases = {}
    for path in paths:
        prim = PurePosixPath(path)
        name = prim.name
        if name.lower() in {"sensor", "lidar", "omnilidar"} and prim.parent.name:
            name = prim.parent.name
        name = re.sub(r"[^A-Za-z0-9_]", "_", name).strip("_") or "lidar"
        if name[0].isdigit():
            name = "lidar_" + name
        bases[path] = name
    counts = Counter(bases.values())
    reserved = {name for name, count in counts.items() if count == 1} | {world_frame}
    used = {world_frame}
    sensors = []
    for path in paths:
        base = bases[path]
        if counts[base] == 1 and base != world_frame:
            sid = base
        else:
            digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:8]
            sid = base + "_" + digest
            suffix = 2
            while sid in used or sid in reserved:
                sid = f"{base}_{digest}_{suffix}"
                suffix += 1
        used.add(sid)
        sensors.append({"id": sid, "prim_path": path, "topic": f"/lidar/{sid}/points",
                        "frame_id": sid, "record": True})
    return sensors


def discover_sensors(stage, world_frame="world", robot_path=None):
    """Scan once. USD traversal omits inactive/unloaded descendants automatically."""
    paths = [str(prim.GetPath()) for prim in stage.Traverse()
             if prim.IsActive() and prim.IsLoaded() and prim.GetTypeName() == "OmniLidar"
             and (not robot_path or str(prim.GetPath()).startswith(robot_path.rstrip('/') + '/'))]
    sensors = sensors_from_paths(paths, world_frame)
    if not sensors:
        raise ValueError("No active, loaded OmniLidar sensors found. Load the sensor assets and run again.")
    return sensors
