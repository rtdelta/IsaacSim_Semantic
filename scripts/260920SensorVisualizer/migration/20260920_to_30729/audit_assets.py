"""Read USD composition dependencies using the NEW instance's USD libraries.

Does not start Kit, simulate, render, execute project scripts, or fetch URLs.
"""
import glob
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, sorted(glob.glob("/root/isaacsim/extscache/omni.usd.libs-*"))[-1])
from pxr import Ar, Sdf

HERE = Path(__file__).resolve().parent
ROOT = Path("/root/gpufree-data")

def main():
    started = time.time()
    asset = ROOT / "IsaacSim_Asset"
    entries = sorted((asset / "combine_stage").glob("*.usda"))
    entries += sorted((asset / "excavator_module_set/Excavator_3DGS_Contract").glob("*.usda"))
    entries += sorted((asset / "sensor_set").rglob("*.usda"))
    layers, missing, external, failures, edges = {}, [], [], [], []
    queue = [str(p) for p in entries]
    seen = set()
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        try:
            layer = Sdf.Layer.FindOrOpen(name)
            if layer is None:
                failures.append({"layer": name, "error": "Sdf could not open layer"})
                continue
            deps = sorted(layer.GetCompositionAssetDependencies())
            layers[name] = deps
            for dep in deps:
                if not dep:
                    continue
                if "://" in dep or (len(dep) > 1 and dep[1] == ":"):
                    external.append({"layer": name, "reference": dep})
                    continue
                relative = Sdf.ComputeAssetPathRelativeToLayer(layer, dep)
                resolved = str(Ar.GetResolver().Resolve(relative))
                edge = {"layer": name, "reference": dep, "resolved": resolved}
                edges.append(edge)
                if not resolved:
                    missing.append(edge)
                elif resolved.lower().endswith((".usd", ".usda", ".usdc", ".usdz")) or "[" in resolved:
                    queue.append(resolved)
        except Exception as exc:
            failures.append({"layer": name, "error": str(exc)})
    report = dict(entrypoints=[str(p) for p in entries], layers_checked=len(layers),
                  dependencies=edges, missing=missing, external=external, failures=failures,
                  elapsed_seconds=round(time.time()-started,2),
                  scope="USD composition references only; no GUI, rendering or simulation test")
    (HERE / "asset_dependencies.json").write_text(json.dumps(report, ensure_ascii=True, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in {"dependencies", "entrypoints"}}))

if __name__ == "__main__":
    main()
