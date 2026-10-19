import json, os, subprocess, sys
from pathlib import Path
code = r'''
import json, sys, hashlib
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from pxr import Ar, Sdf, Usd, UsdGeom
p=Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda')
s=Usd.Stage.Open(str(p),load=Usd.Stage.LoadNone)
s.Load('/environment_Fangshan_02')
lights=[]
for prim in s.Traverse():
    if prim.GetTypeName()!='DomeLight': continue
    parent=prim.GetParent()
    row=dict(path=str(prim.GetPath()),active=prim.IsActive(),visibility=str(UsdGeom.Imageable(prim).ComputeVisibility()),attrs={},
        parent=dict(path=str(parent.GetPath()),visibility=str(parent.GetAttribute('visibility').Get()),
                    computed_visibility=str(UsdGeom.Imageable(parent).ComputeVisibility())))
    for a in prim.GetAttributes():
        if not a.HasAuthoredValueOpinion(): continue
        v=a.Get()
        row['attrs'][a.GetName()]=dict(value=str(v),layers=[str(sp.layer.identifier) for sp in a.GetPropertyStack()])
        if a.GetTypeName()==Sdf.ValueTypeNames.Asset and v:
            asset=Ar.GetResolver().OpenAsset(Ar.ResolvedPath(v.resolvedPath)) if v.resolvedPath else None
            row['attrs'][a.GetName()].update(resolved=v.resolvedPath,bytes=asset.GetSize() if asset else None)
    lights.append(row)
print(json.dumps(dict(scene=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),domelights=lights,
    root_metadata=str(s.GetRootLayer().customLayerData),composition_errors=[str(e) for e in s.GetCompositionErrors()])))
'''
libs=sorted(Path('/root/isaacsim/extscache').glob('omni.usd.libs-*'))[-1]
env=dict(os.environ);env['LD_LIBRARY_PATH']=str(next(libs.rglob('libusd_tf.so')).parent)+':/root/isaacsim/kit/lib'
r=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(libs)],env=env,capture_output=True,text=True,timeout=30)
print(json.dumps(dict(exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr)));raise SystemExit(r.returncode)
