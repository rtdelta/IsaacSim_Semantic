"""Prepare a new experiment directory without writing old paths."""
from pathlib import Path
import json,hashlib,shutil,time,subprocess,sys,os
root=Path(__file__).resolve().parent
previous=Path("/root/gpufree-data/diagnostics/bvh_causality_20260917_083739")
binary=Path("/root/isaacsim/extscache/omni.hydra.rtx-1.0.4+f9bf0dda.lx64.r/bin/deps/librtx.scenedb.plugin.so")
def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(4*1024*1024),b""):h.update(b)
    return h.hexdigest()
if sys.argv[1]=="prepare":
    active=[]
    for p in Path("/proc").iterdir():
        if p.name.isdigit():
            try:
                exe=os.readlink(p/"exe")
                if exe.startswith("/root/isaacsim/"):active.append({"pid":int(p.name),"exe":exe})
            except OSError:pass
    if active:raise RuntimeError("Existing Isaac process: "+str(active))
    before=json.loads((previous/"protected_before.json").read_text())
    paths=set(Path(p) for p in before)
    for diag in previous.parent.iterdir():
        if diag.is_dir() and diag!=root:
            paths.update(p for p in diag.iterdir() if p.is_file() and p.suffix in [".py",".md",".json",".txt",".usda",".usd"])
    paths.add(binary)
    manifest={str(p):{"bytes":p.stat().st_size,"sha256":sha(p)} for p in sorted(paths)}
    if not (root/"protected_before.json").exists():
        with (root/"protected_before.json").open("x") as f:json.dump(manifest,f,indent=2)
    else:
        saved=json.loads((root/"protected_before.json").read_text())
        if saved!=manifest:raise RuntimeError("Protected files changed during preparation")
    assert manifest[str(binary)]["sha256"]=="3fc6bb790d164decaf40aa52c5c76a6401e67e210f395e40cea9ea20ac6c57f0"
    for rel in ["debug_tools/gdb_root","runtime_seed/cache/ov","runtime_seed/portable/cache","runtime_seed/cuda_cache","runtime_seed/gl_cache"]:
        src=previous/rel
        if src.exists():
            dst=root/rel;dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copytree(src,dst,symlinks=False,ignore_dangling_symlinks=True,dirs_exist_ok=True)
    (root/"debug_python.py").chmod(0o755)
    data={"protected_count":len(manifest),"binary_sha256":manifest[str(binary)]["sha256"],"previous":str(previous),"ready_at":time.time(),"active_isaac_processes_before":active}
    with (root/"environment_before.json").open("x") as f:json.dump(data,f,indent=2)
    print(json.dumps(data),flush=True)
else:
    before=json.loads((root/"protected_before.json").read_text())
    result={"checked":len(before),"changed":[],"missing":[],"verified_at":time.time()}
    for name,info in before.items():
        p=Path(name)
        if not p.exists():result["missing"].append(name)
        elif sha(p)!=info["sha256"]:result["changed"].append(name)
    with (root/("verification_"+str(time.time_ns())+".json")).open("x") as f:json.dump(result,f,indent=2)
    print(json.dumps(result),flush=True)
