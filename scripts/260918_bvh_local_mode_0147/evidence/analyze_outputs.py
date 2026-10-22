"""Analyze static returns by emitter/tick/echo, and analytic mesh ray times."""
from pathlib import Path
import json,sys,numpy as np,collections
root=Path(__file__).resolve().parent
def quant(x):
    x=np.asarray(x)
    if not len(x):return None
    return dict(zip(["min","p50","p95","max"],map(float,np.quantile(x,[0,.5,.95,1]))))
def measured(name):
    p=root/"cases"/name
    if not (p/"result.json").exists():return p,None,[]
    j=json.loads((p/"result.json").read_text())
    return p,j,[s for s in j.get("samples",[]) if s.get("measurement") and s.get("file")]
def key(a):
    return a["emitterId"].astype(np.int64)*1000000+a["tickId"].astype(np.int64)*10+a["echoId"].astype(np.int64)
def compare(na,nb):
    pa,ja,ra=measured(na);pb,jb,rb=measured(nb)
    if not ra or not rb:return None
    rb={s["frame"]:s for s in rb}
    counts=collections.Counter();ds=[];df=[];di=[];allxyzexact=True
    for sa in ra:
        if sa["frame"] not in rb:continue
        sb=rb[sa["frame"]]
        aa=np.load(pa/sa["file"]);ab=np.load(pb/sb["file"])
        ka,kb=key(aa),key(ab)
        assert len(np.unique(ka))==len(ka) and len(np.unique(kb))==len(kb)
        k,ia,ib=np.intersect1d(ka,kb,return_indices=True)
        da=np.linalg.norm(aa["xyz"][ia],axis=1);db=np.linalg.norm(ab["xyz"][ib],axis=1)
        va=(aa["flags"][ia]&64)!=0;vb=(ab["flags"][ib]&64)!=0
        an=(da<8)&(da>0)&va;bn=(db<8)&(db>0)&vb
        counts.update(scans=1,common=len(k),only_a=len(ka)-len(k),only_b=len(kb)-len(k),near_both=int((an&bn).sum()),near_a_only=int((an&~bn).sum()),near_b_only=int((bn&~an).sum()))
        ds.extend((db-da)[an&bn].tolist())
        df.extend((db-da)[~an&~bn&va&vb].tolist())
        if "scalar" in aa and "scalar" in ab:di.extend((ab["scalar"][ib]-aa["scalar"][ia])[an&bn].tolist())
        allxyzexact &= np.array_equal(aa["xyz"],ab["xyz"]) and np.array_equal(ka,kb)
    return {"a":na,"b":nb,"counts":dict(counts),"xyz_and_keys_bit_exact":bool(allxyzexact),"common_near_abs_range_difference_m":quant(np.abs(ds)),"common_near_signed_range_difference_m":quant(ds),"common_far_abs_range_difference_m":quant(np.abs(df)),"common_near_abs_scalar_difference":quant(np.abs(di))}
def case_summary(name):
    p,j,rows=measured(name)
    if j is None:return {"case":name,"status":"pending"}
    d={"case":name,"status":j["status"],"error":j.get("error"),"measured":len(rows)}
    if not rows:return d
    near=[];finite=0;valid=0;total=0
    for s in rows:
        a=np.load(p/s["file"]);dist=np.linalg.norm(a["xyz"],axis=1);v=((a["flags"]&64)!=0)&np.isfinite(dist)&(dist>0)
        near.append(int((v&(dist<8)).sum()));finite+=int(np.isfinite(a["xyz"]).all(axis=1).sum());valid+=int(v.sum());total+=len(dist)
    d.update(near_hits=quant(near),finite=finite,valid=valid,total=total,engine_flags=[x["flags"] for x in j["snapshots"]["final"]["engines"]])
    ev=[json.loads(x) for x in (p/"native_trace.jsonl").read_text().splitlines()]
    d["native_counts"]=dict(collections.Counter(x["event"] for x in ev))
    d["effective_modes"]=dict(collections.Counter(str((x["mode_original"],x["mode_effective"])) for x in ev if x["event"]=="build_entry"))
    if j["args"]["geometry"]=="mesh" and not j["args"].get("native_nz3"):
        errors=[];direction_errors=[];frame_pose_errors=[]
        elev=np.deg2rad(np.array([-15,-10,-5,0,3,5,10,15]))
        for s in rows:
            a=np.load(p/s["file"]);t=(s["timestampNs"]+a["timeOffsetNs"].astype(float))*1e-9
            angle=-a["timeOffsetNs"].astype(float)*1e-9*10*2*np.pi
            el=elev[a["emitterId"]]
            direction=np.column_stack([np.cos(el)*np.cos(angle),np.cos(el)*np.sin(angle),np.sin(el)])
            origin=np.zeros_like(direction)
            updates=j["updates"]
            pt=np.array([u["timeline_time"] for u in updates])
            px=np.array([u["poses"]["sensor"][3][0] for u in updates])
            assert t.min()>=pt.min() and t.max()<=pt.max(), "No pose extrapolation"
            origin[:,0]=np.interp(t,pt,px)
            with np.errstate(divide="ignore",invalid="ignore"):
                candidates=np.where(np.abs(direction)>1e-10,(np.where(direction>=0,10.,-10.)-origin)/direction,np.inf)
            predicted=np.min(candidates,axis=1)
            valid=((a["flags"]&64)!=0)&np.isfinite(a["xyz"]).all(axis=1)&(np.linalg.norm(a["xyz"],axis=1)>.1)
            errors.extend(np.linalg.norm(a["xyz"]-direction*predicted[:,None],axis=1)[valid].tolist())
            dist=np.linalg.norm(a["xyz"],axis=1)
            direction_errors.extend(np.linalg.norm(a["xyz"]/dist[:,None]-direction,axis=1)[valid].tolist())
            if j["args"]["motion"]=="sensor":
                for keyname in ["frameStart","frameEnd"]:
                    f=s[keyname];frame_pose_errors.append(f["position"][0]-j["args"]["speed"]*f["timestampNs"]*1e-9)
        d["analytic_xyz_error_m"]=quant(errors)
        d["direction_vector_error"]=quant(direction_errors)
        d["gmo_frame_pose_minus_velocity_times_timestamp_m"]=quant(frame_pose_errors)
    return d
names=sorted(p.name for p in (root/"cases").iterdir() if p.is_dir())
data={"cases":[case_summary(n) for n in names if ("_r" in n and n.startswith("lidar_")) or n.startswith("motion_")],
      "comparisons":[compare(a,b) for a,b in [("lidar_A_r1","lidar_A_r2"),("lidar_A_r2","lidar_A_r3"),("lidar_C_r1","lidar_C_r2"),("lidar_C_r2","lidar_C_r3"),("lidar_A_r2","lidar_C_r2"),("lidar_E_r1","lidar_F_r1"),("lidar_A_r1","lidar_D_r1")]]}
if len(sys.argv)>1:
    with (root/sys.argv[1]).open("x") as f:json.dump(data,f,indent=2,allow_nan=False)
else:print(json.dumps(data,indent=2))
