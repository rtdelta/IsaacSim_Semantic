"""Read-only fingerprints of existing user files; output exclusively in this new directory."""
import json,hashlib,sys,time
from pathlib import Path
root=Path(__file__).resolve().parent
def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(4*1024*1024),b""):h.update(b)
    return h.hexdigest()
if sys.argv[1]=="before":
    paths=set()
    baseline=json.loads(Path("/root/gpufree-data/diagnostics/motion_bvh_20260917_032416/source_usda_before.json").read_text())
    paths.update(Path(p) for p in baseline)
    project=Path("/root/gpufree-data/semantic/scripts/260907LidarVisualizer")
    skip={"__pycache__","node_modules",".git"}
    for p in project.rglob("*"):
        if p.is_file() and p.suffix in [".py",".sh",".json",".toml",".yaml",".yml",".md",".usda",".usd",".usdc"] and not any(x in skip for x in p.parts):paths.add(p)
    paths.add(Path("/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Sim_Fangshan_02/3dgs_usd/tooth_01_front.usd"))
    d={str(p):{"bytes":p.stat().st_size,"sha256":sha(p)} for p in sorted(paths) if p.exists()}
    with (root/"protected_before.json").open("x") as f:json.dump(d,f,indent=2)
    print(json.dumps({"protected_files":len(d),"bytes":sum(x["bytes"] for x in d.values())}))
else:
    d=json.loads((root/"protected_before.json").read_text())
    v={"checked":len(d),"changed":[],"missing":[]}
    for s,m in d.items():
        p=Path(s)
        if not p.exists():v["missing"].append(s)
        elif sha(p)!=m["sha256"]:v["changed"].append(s)
    dest=root/("verification_"+str(time.time_ns())+".json")
    dest.write_text(json.dumps(v,indent=2));print(json.dumps(v))

