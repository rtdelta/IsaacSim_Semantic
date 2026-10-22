"""Verify completed case contracts and protected old files; never modifies old paths."""
from pathlib import Path
import json,collections,subprocess,os,time,ast,hashlib
r=Path(__file__).resolve().parent
for p in r.glob("*.py"):ast.parse(p.read_text())
cases=[];failures=[];excluded=[]
for p in sorted((r/"cases").iterdir()):
    if not p.is_dir():continue
    process=json.loads((p/"process.json").read_text())
    j=json.loads((p/"result.json").read_text())
    row={"case":p.name,"status":j["status"],"exit_code":process.get("exit_code"),"timed_out":process.get("timed_out"),"duration":process.get("duration"),"geometry":j["args"]["geometry"],"output":j["args"]["output"],"global_bvh":j["args"]["bvh"]}
    if j["status"]!="collected":
        row["error"]=j.get("error")
        if p.name in ["lidar_"+c for c in "ABCDEF"] and "Invalid sensor attribute auxOutputType" in j.get("error",""):excluded.append(p.name)
        else:failures.append({"case":p.name,"problem":"unexpected result status"})
    else:
        if process.get("timed_out") or process.get("exit_code")!=0:failures.append({"case":p.name,"problem":"process unsuccessful"})
        if not j.get("isolation",{}).get("verified"):failures.append({"case":p.name,"problem":"output isolation"})
        flags=[x["flags"] for x in j["snapshots"]["final"]["engines"]]
        if flags!=[int(j["args"]["bvh"])]:failures.append({"case":p.name,"problem":"engine flags","actual":flags})
        events=[json.loads(x) for x in (p/"native_trace.jsonl").read_text().splitlines()]
        traces=[x for x in events if x["event"]=="trace_summary"]
        if len(traces)!=1 or traces[0]["counts"]["errors"]:failures.append({"case":p.name,"problem":"native trace"})
        else:
            trace=traces[0];count=trace["counts"]
            row["trace"]=count
            if j["args"]["geometry"]=="mesh":
                if count["entries"]:failures.append({"case":p.name,"problem":"Gaussian hook affected mesh"})
            else:
                expected_modified=count["entries"] if trace["intervene"] and j["args"]["bvh"] else 0
                expected_normal=count["entries"] if not j["args"]["bvh"] or trace["intervene"] else 0
                if not count["entries"] or count["modified"]!=expected_modified or count["normal_call"]!=expected_normal or count["normal_return"]!=expected_normal:
                    failures.append({"case":p.name,"problem":"native intervention contract"})
        samples=[x for x in j["samples"] if x.get("measurement")]
        row["measured_outputs"]=len(samples)
        row["unique_timestampNs"]=len(set(x.get("timestampNs") for x in samples))
        if any(x["finite"]!=x["count"] for x in samples):failures.append({"case":p.name,"problem":"nonfinite points"})
        if j["args"]["output"]=="lidar" and not samples:failures.append({"case":p.name,"problem":"empty output"})
    cases.append(row)
protection=subprocess.run(["python3",str(r/"prepare_protect.py"),"verify"],capture_output=True,text=True,check=True)
protection=json.loads(protection.stdout)
if protection["changed"] or protection["missing"]:failures.append({"problem":"old files changed","detail":protection})
active=[]
for p in Path("/proc").iterdir():
    if not p.name.isdigit():continue
    try:
        exe=os.readlink(p/"exe")
        if exe.startswith("/root/isaacsim/") or exe.startswith(str(r/"debug_tools")):active.append({"pid":int(p.name),"exe":exe})
    except OSError:pass
if active:failures.append({"problem":"Isaac/debugger still active","detail":active})
out={"completed_at":time.time(),"cases":cases,"attempt_count":len(cases),"collected_count":sum(x["status"]=="collected" for x in cases),"excluded_preparation_failures":excluded,"failures":failures,"source_protection":protection,"active_isaac_or_debugger":active,"all_checks_pass":not failures}
with (r/"validation_final.json").open("x") as f:json.dump(out,f,indent=2)
print(json.dumps({k:v for k,v in out.items() if k!="cases"},indent=2))

