"""Compact case inventory; does not modify any case data."""
from pathlib import Path
import json,sys,collections
root=Path(__file__).resolve().parent
rows=[]
for case in sorted((root/"cases").iterdir()):
    if not case.is_dir():continue
    row={"case":case.name}
    for name,key in [("process.json","process"),("result.json","result")]:
        if (case/name).exists():
            d=json.loads((case/name).read_text())
            if key=="process":row.update({k:d.get(k) for k in ["exit_code","timed_out","duration","pid"]})
            else:
                row.update(status=d.get("status"),error=d.get("error"),isolation=d.get("isolation"),images=d.get("images"),gmo_schema=d.get("gmo_schema"),unavailable_gmo_fields=d.get("unavailable_gmo_fields"))
                row["engines"]=d.get("snapshots",{}).get("final",{}).get("engines",[])
                samples=[s for s in d.get("samples",[]) if s.get("measurement")]
                row["samples"]=len(samples)
                row["complete_samples"]=sum(s["scan_complete"]!=0 for s in samples)
                for field in ["count","near_hits_lt8m","range_min","range_max","near_intensity_mean"]:
                    vals=[s[field] for s in samples if s.get(field) is not None]
                    if vals:row[field]=[min(vals),max(vals)]
    if "status" not in row and (case/"progress.json").exists():
        d=json.loads((case/"progress.json").read_text());row["phase"]=d.get("phase");row["last_event"]=d.get("events",[None])[-1]
    trace=case/"native_trace.jsonl"
    if trace.exists():
        events=[]
        for line in trace.read_text().splitlines():
            try:events.append(json.loads(line))
            except ValueError:pass
        row["trace_events"]=dict(collections.Counter(x["event"] for x in events))
        row["trace_summary"]=[x for x in events if x["event"]=="trace_summary"]
        row["trace_errors"]=[x for x in events if x["event"]=="trace_error"]
        row["init_modes"]=[x["mode"] for x in events if x["event"]=="init_call"]
        row["mode_pairs"]=dict(collections.Counter(str((x["mode_original"],x["mode_effective"])) for x in events if x["event"]=="build_entry"))
        row["command_modules"]=sorted(set(x.get("command_module") or "" for x in events if x["event"]=="normal_build_call"))
        row["task_modes"]=sorted(set(x["task_mode"] for x in events if x["event"]=="callback_return"))
    logs=[p for p in [case/"kit.log",case/"console.log",case/"debugger.log"] if p.exists()]
    err=[]
    for log in logs:
        for line in log.read_text(errors="replace").splitlines():
            if any(x in line for x in ["Gaussians do not support","trace_error","Traceback","received signal SIGSEGV","GPU crash"]):err.append({"file":log.name,"line":line[:700]})
    row["relevant_errors"]=err
    rows.append(row)
data={"cases":rows}
if len(sys.argv)>1:
    with (root/sys.argv[1]).open("x") as f:json.dump(data,f,indent=2)
else:print(json.dumps(data,indent=2))
