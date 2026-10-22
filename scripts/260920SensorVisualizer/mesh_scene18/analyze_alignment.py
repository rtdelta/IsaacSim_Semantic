"""Recover and cross-validate the historical mesh coordinate transform."""
import json
from pathlib import Path
import numpy as np
from pxr import Usd, UsdGeom

ROOT=Path('/root/gpufree-data/IsaacSim_Asset')
OLD=ROOT/'excavator_module_set/Sim_Fangshan_02'
NEW=ROOT/'excavator_module_set/Excavator_3DGS_Contract'
MAPPING=[('track','track','track'),('cab','operator_cab','operator_cab'),('boom','boom','boom'),('arm','small_arm','small_arm')]

def positions(path):
    stage=Usd.Stage.Open(str(path))
    prim=next(p for p in stage.Traverse() if p.GetAttribute('positions').HasAuthoredValueOpinion())
    return np.asarray(prim.GetAttribute('positions').Get(),dtype=np.float64)

def fit_rigid(x,y):
    xc=x.mean(axis=0);yc=y.mean(axis=0)
    u,s,vt=np.linalg.svd((x-xc).T@(y-yc))
    d=np.eye(3);d[-1,-1]=np.linalg.det(u@vt)
    r=u@d@vt;t=yc-xc@r
    m=np.eye(4);m[:3,:3]=r;m[3,:3]=t
    return m

def apply(points,m):return points@m[:3,:3]+m[3,:3]
def error(a,b):
    e=np.linalg.norm(a-b,axis=1)
    return {'count':len(e),'max':float(e.max()),'rms':float(np.sqrt(np.mean(e*e))),'median':float(np.median(e))}

raw=positions(NEW/'geometry/track.usdc');aligned=positions(OLD/'3dgs_usd/track.usd')
matrix=fit_rigid(raw,aligned)
report={'matrix_convention':'row vectors: corrected = raw @ R + translation', 'raw_to_corrected':matrix.tolist(), 'corrected_to_raw':np.linalg.inv(matrix).tolist(),'gaussian_checks':{},'mesh_checks':{}}
for current,old,mesh in MAPPING:
    a=positions(NEW/'geometry'/f'{current}.usdc');b=positions(OLD/'3dgs_usd'/f'{old}.usd')
    if len(a)==len(b):report['gaussian_checks'][current]=error(apply(a,matrix),b)
    else:report['gaussian_checks'][current]={'raw_count':len(a),'aligned_count':len(b),'reason':'different count; no assumed index pairing'}
source=Usd.Stage.Open(str(ROOT/'excavator_module_set/sim_Fangshan_01/mechanic_parts_set/mesh_parts/拆分成五部分的mesh.usd'))
mp=source.GetPrimAtPath('/World/mesh_')
pts=np.asarray(mp.GetAttribute('points').Get(),dtype=np.float64)
report['raw_mesh_attributes']=[{'name':a.GetName(),'type':str(a.GetTypeName())} for a in mp.GetAttributes() if a.HasAuthoredValueOpinion()]
dest=Usd.Stage.Open(str(OLD/'waji_mesh_corrected.usdc'))
for prim in dest.Traverse():
    if not prim.IsA(UsdGeom.Mesh):continue
    name=prim.GetName().removesuffix('_mesh')
    dp=np.asarray(prim.GetAttribute('points').Get(),dtype=np.float64)
    attr=mp.GetAttribute('primvars:Group_'+name)
    row={'corrected_vertices':len(dp)}
    if attr and attr.HasAuthoredValueOpinion():
        weights=np.asarray(attr.Get());mask=weights>0.5;selected=pts[mask]
        row['raw_vertices']=len(selected)
        if len(selected)==len(dp):row['index_correspondence_error']=error(apply(selected,matrix),dp)
    report['mesh_checks'][name]=row
report['readme']=(OLD/'README.md').read_text()[:10000]
try:
    from scipy.spatial import cKDTree
    corrected=np.concatenate([np.asarray(p.GetAttribute('points').Get(),dtype=np.float64) for p in dest.Traverse() if p.IsA(UsdGeom.Mesh)])
    predicted=apply(pts,matrix)
    distance,_=cKDTree(corrected).query(predicted,workers=2)
    reverse,_=cKDTree(predicted).query(corrected,workers=2)
    report['mesh_global_correspondence']={'source_vertices':len(pts),'corrected_vertices':len(corrected),'forward_max':float(distance.max()),'reverse_max':float(reverse.max()),'forward_rms':float(np.sqrt(np.mean(distance**2))),'scipy_available':True}
except ImportError:
    corrected=np.concatenate([np.asarray(p.GetAttribute('points').Get(),dtype=np.float64) for p in dest.Traverse() if p.IsA(UsdGeom.Mesh)])
    predicted=apply(pts,matrix)
    def rowkeys(a):
        a=np.ascontiguousarray(np.rint(a*1000).astype(np.int64))
        return a.view(np.dtype((np.void,a.dtype.itemsize*3))).ravel()
    distances=[]
    for point in predicted[np.linspace(0,len(predicted)-1,128,dtype=int)]:
        distances.append(float(np.sqrt(np.min(np.sum((corrected-point)**2,axis=1)))))
    report['mesh_global_correspondence']={'scipy_available':False,'source_vertices':len(pts),'corrected_vertices':len(corrected),'rounded_1mm_vertex_match_fraction':float(np.mean(np.isin(rowkeys(predicted),rowkeys(corrected)))),'sampled_128_nearest_vertex_max':max(distances),'source_bounds':predicted.min(axis=0).tolist()+predicted.max(axis=0).tolist(),'corrected_bounds':corrected.min(axis=0).tolist()+corrected.max(axis=0).tolist()}
print(json.dumps(report,ensure_ascii=False))
