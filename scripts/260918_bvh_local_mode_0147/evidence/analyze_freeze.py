"""Compare finite representative rays to the same Gaussian frozen at recorded ray-time poses."""
from pathlib import Path
import json,sys,numpy as np
r=Path(__file__).resolve().parent
mapping=json.loads((r/"freeze_mapping.json").read_text())
rows=[]
for m in mapping:
    p=r/"cases"/m["moving_case"];q=r/"cases"/m["frozen_case"]
    if not (q/"result.json").exists():continue
    jm=json.loads((p/"result.json").read_text());jf=json.loads((q/"result.json").read_text())
    sm=next(s for s in jm["samples"] if s.get("frame")==m["moving_frame"] and s.get("file"))
    sf=next(s for s in jf["samples"] if s.get("frame")==m["moving_frame"] and s.get("file"))
    assert sm["timestampNs"]==sf["timestampNs"]==m["timestampNs"]
    am=np.load(p/sm["file"]);af=np.load(q/sf["file"])
    def selected(a):
        ids=np.where((a["tickId"]==m["tickId"])&(a["timeOffsetNs"]==m["timeOffsetNs"])&(a["echoId"]==0))[0]
        return {int(a["emitterId"][i]):i for i in ids}
    mi=selected(am);fi=selected(af)
    for eid in sorted(set(mi)|set(fi)):
        d={**m,"emitterId":eid,"moving_exists":eid in mi,"frozen_exists":eid in fi}
        for label,inds,a in [("moving",mi,am),("frozen",fi,af)]:
            if eid in inds:
                i=inds[eid];x=a["xyz"][i];d[label+"_xyz"]=x.tolist();d[label+"_range"]=float(np.linalg.norm(x));d[label+"_flags"]=int(a["flags"][i]);d[label+"_scalar"]=float(a["scalar"][i])
        if eid in mi and eid in fi:
            d["xyz_difference_m"]=float(np.linalg.norm(am["xyz"][mi[eid]]-af["xyz"][fi[eid]]))
            d["both_near_7m"]=d["moving_range"]<7 and d["frozen_range"]<7
        rows.append(d)
summary=[]
for motion in ["sensor","gaussian"]:
 for mode in [0,1]:
    rr=[x for x in rows if x["moving_case"]==f"motion_gaussian_{motion}_{mode}"]
    matched=[x for x in rr if x.get("both_near_7m")]
    dif=[x["xyz_difference_m"] for x in matched]
    summary.append({"motion":motion,"bvh":mode,"representative_rays_union":len(rr),"near_both":len(matched),"near_status_mismatch":sum((x.get("moving_range",100)<7)!=(x.get("frozen_range",100)<7) for x in rr),"missing_one_side":sum(x["moving_exists"]!=x["frozen_exists"] for x in rr),"near_xyz_difference_m":dict(zip(["min","p50","p95","max"],map(float,np.quantile(dif,[0,.5,.95,1])))) if dif else None})
out={"method":"Frozen reference uses the same global mode and same Gaussian-local ordinary build to control observed mode-dependent sampling-sequence changes. Ray IDs, timestamp, tick, direction, output update index match. Pose is independently interpolated from recorded transforms, not fitted from point returns. Only two scan times, eight emitters at tick 1 each, per motion/mode.","completed_frozen_cases":len(set(x["frozen_case"] for x in rows)),"summary":summary,"rays":rows}
with (r/sys.argv[1]).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
print(json.dumps({"completed_frozen_cases":out["completed_frozen_cases"],"summary":summary},indent=2))

