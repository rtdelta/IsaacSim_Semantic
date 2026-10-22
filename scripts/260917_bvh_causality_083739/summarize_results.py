"""Summarize completed experiments without rewriting any prior evidence."""
import json,re,sys,time
from pathlib import Path
root=Path(__file__).resolve().parent
rows=[]
for d in sorted((root/"cases").iterdir()):
 if not d.is_dir():continue
 p=d/"result.json";proc=d/"process.json"
 row={"case":d.name}
 if proc.exists():row["process"]=json.loads(proc.read_text())
 if not p.exists():
  row["status"]="no_result";rows.append(row);continue
 r=json.loads(p.read_text())
 row.update(status=r["status"],args=r["args"],error=r.get("error"),
            isolation=r.get("isolation"),images=r.get("images",[]))
 snap=r.get("snapshots",{}).get("final",{})
 row["engines"]=snap.get("engines",[]);row["settings"]=snap.get("settings",{})
 row["gaussians"]=snap.get("gaussians",[]);row["active_lidars"]=snap.get("lidars",[])
 row["render_product_count"]=len(snap.get("render_products",[]))
 logpath=d/("debugger.log" if (d/"debugger.log").exists() else "console.log")
 lines=logpath.read_text(errors="replace").splitlines() if logpath.exists() else []
 row["gaussian_errors"]=[l for l in lines if "Gaussians do not support motion BVH" in l]
 row["other_errors"]=[l for l in lines if "[Error]" in l and "Gaussians do not support motion BVH" not in l][:8]
 row["motion_warnings"]=[l for l in lines if "MotionBVH for lidar model not enabled" in l or "Multi-tick is enabled but motion BVH is not active" in l]
 samples=[s for s in r["samples"] if s.get("measurement")]
 row["lidar"]={"samples":len(samples),"counts":sorted(set(s["count"] for s in samples)),
    "near_hits_min":min([s["near_hits_lt8m"] for s in samples],default=None),
    "near_hits_max":max([s["near_hits_lt8m"] for s in samples],default=None),
    "complete":sum(bool(s["scan_complete"]) for s in samples),
    "range_min":min([s["range_min"] for s in samples],default=None)}
 trace=d/"native_trace.jsonl"
 if trace.exists():row["native_trace"]=[json.loads(l) for l in trace.read_text().splitlines() if l]
 rows.append(row)
target=root/(sys.argv[1] if len(sys.argv)>1 else "summary_"+str(time.time_ns())+".json")
with target.open("x") as f:json.dump(rows,f,indent=2)
for r in rows:
 if r["status"]=="collected":
  print(r["case"],"gs_errors",len(r.get("gaussian_errors",[])),"near",r.get("lidar",{}).get("near_hits_max"),
       "engine_flags",[e["flags"] for e in r.get("engines",[])],
       "trace_modes",[t["mode"] for t in r.get("native_trace",[]) if "mode" in t])
print("SUMMARY",target)

