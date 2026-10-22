"""Supplementary paired geometry invariants and sampling-sequence checks."""
from pathlib import Path
import json,sys,numpy as np,collections
root=Path(__file__).resolve().parent
def quant(x):
    x=np.asarray(x)
    return dict(zip(["min","p50","p95","max"],map(float,np.quantile(x,[0,.5,.95,1])))) if len(x) else None
def rows(name):
    p=root/"cases"/name;j=json.loads((p/"result.json").read_text())
    return p,j,{x["frame"]:x for x in j["samples"] if x.get("file")}
def key(a):return a["emitterId"].astype("int64")*1000000+a["tickId"].astype("int64")*10+a["echoId"]
def pairs(na,nb,lag=0,threshold=6,selector="near"):
    pa,ja,ra=rows(na);pb,jb,rb=rows(nb)
    result={"a":na,"b":nb,"lag":lag,"selection":selector,"threshold_m":threshold}
    count=collections.Counter();err=[];scalar=[];ranges_a=[];ranges_b=[]
    for f,sa in ra.items():
        if f+lag not in rb:continue
        a=np.load(pa/sa["file"]);b=np.load(pb/rb[f+lag]["file"])
        kk,ia,ib=np.intersect1d(key(a),key(b),return_indices=True)
        xa=a["xyz"][ia];xb=b["xyz"][ib];da=np.linalg.norm(xa,axis=1);db=np.linalg.norm(xb,axis=1)
        na=(da<threshold)&(da>.1);nb=(db<threshold)&(db>.1)
        if selector=="back_hemisphere":
            sel=(xa[:,0]/da<-.05)
        else:sel=na&nb
        count.update(scans=1,common=len(kk),selected=int(sel.sum()),near_mismatch=int((na^nb).sum()))
        err.extend(np.linalg.norm(xa[sel]-xb[sel],axis=1))
        ranges_a.extend(da[na]);ranges_b.extend(db[nb])
        if "scalar" in a and "scalar" in b:scalar.extend(np.abs(a["scalar"][ia][sel]-b["scalar"][ib][sel]))
    result.update(counts=dict(count),xyz_absolute_difference_m=quant(err),scalar_absolute_difference=quant(scalar),a_range=quant(ranges_a),b_range=quant(ranges_b))
    if ranges_a and ranges_b:
        av=np.sort(ranges_a);bv=np.sort(ranges_b);v=np.sort(np.concatenate([av,bv]))
        result["pooled_range_empirical_cdf_max_difference"]=float(np.abs(np.searchsorted(av,v,side="right")/len(av)-np.searchsorted(bv,v,side="right")/len(bv)).max())
    return result
out={"note":"Invariants compare the same Gaussian and same mode, not a mesh approximation; statistical comparisons are descriptive, not equivalence tests.",
"comparisons":[]}
for b in [0,1]:
    out["comparisons"].append(pairs(f"motion_gaussian_none_{b}",f"motion_gaussian_both_{b}"))
    out["comparisons"].append(pairs(f"motion_gaussian_sensor_{b}",f"motion_gaussian_reverse_{b}"))
    out["comparisons"].append(pairs(f"motion_mesh_sensor_{b}",f"motion_gaussian_sensor_{b}",selector="back_hemisphere"))
for na,nb,lag in [("lidar_A_r2","lidar_C_r2",0),("lidar_A_r2","lidar_A_r2",1),("lidar_C_r2","lidar_C_r2",1)]:
    out["comparisons"].append(pairs(na,nb,lag,threshold=8))
with (root/sys.argv[1]).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)

