"""Sensitivity controls: correct frozen pose versus deliberately displaced frozen pose."""
from pathlib import Path
import json,sys,numpy as np
r=Path(__file__).resolve().parent
mapping=json.loads((r/"freeze_controls_mapping.json").read_text())
rows=[]
for m in mapping:
    ps=[]
    for n in [m["reference_frozen_case"],m["frozen_case"]]:
        p=r/"cases"/n
        if not (p/"result.json").exists():break
        j=json.loads((p/"result.json").read_text())
        s=next(s for s in j["samples"] if s.get("frame")==m["moving_frame"] and s.get("file"))
        a=np.load(p/s["file"])
        ix=np.where((a["tickId"]==m["tickId"])&(a["timeOffsetNs"]==m["timeOffsetNs"])&(a["echoId"]==0))[0]
        ps.append((a,{int(a["emitterId"][i]):i for i in ix}))
    if len(ps)!=2:continue
    (a,ia),(b,ib)=ps;rr=[]
    for e in sorted(set(ia)|set(ib)):
        row={"emitterId":e,"reference_exists":e in ia,"wrong_exists":e in ib}
        for label,data,idx in [("reference",a,ia),("wrong",b,ib)]:
            if e in idx:row[label+"_range"]=float(np.linalg.norm(data["xyz"][idx[e]]))
        if e in ia and e in ib:
            row["xyz_difference_m"]=float(np.linalg.norm(a["xyz"][ia[e]]-b["xyz"][ib[e]]))
            row["both_near_7m"]=row["reference_range"]<7 and row["wrong_range"]<7
        rr.append(row)
    vals=[x["xyz_difference_m"] for x in rr if x.get("both_near_7m")]
    rows.append({**m,"rays":rr,"near_both":len(vals),"near_mismatch":sum((x.get("reference_range",100)<7)!=(x.get("wrong_range",100)<7) for x in rr),"near_xyz_difference_m":dict(zip(["min","p50","p95","max"],map(float,np.quantile(vals,[0,.5,.95,1])))) if vals else None})
with (r/sys.argv[1]).open("x") as f:json.dump({"controls":rows},f,indent=2)
print(json.dumps([{k:v for k,v in x.items() if k!="rays"} for x in rows],indent=2))

