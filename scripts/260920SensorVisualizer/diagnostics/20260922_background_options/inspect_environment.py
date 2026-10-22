import json, os, subprocess, sys
from pathlib import Path
code = r'''
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from pxr import Sdf, Usd, UsdGeom, UsdShade, Ar
path='/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda'
s=Usd.Stage.Open(path,load=Usd.Stage.LoadNone)
s.SetEditTarget(s.GetSessionLayer())
s.OverridePrim('/environment_Fangshan_02/changjing4').SetActive(True)
s.Load('/environment_Fangshan_02')
rows=[]
for p in Usd.PrimRange(s.GetPrimAtPath('/environment_Fangshan_02'),Usd.PrimAllPrimsPredicate):
    assets=[]
    for a in p.GetAttributes():
        if a.GetTypeName()==Sdf.ValueTypeNames.Asset:
            v=a.Get()
            if v and v.path: assets.append(dict(name=a.GetName(),authored=v.path,resolved=v.resolvedPath))
    if len(rows)<120:
        rows.append(dict(path=str(p.GetPath()),type=p.GetTypeName(),active=p.IsActive(),
            visibility=str(p.GetAttribute('visibility').Get()),assets=assets,
            geometry=bool(p.GetAttribute('positions')),children=len(p.GetAllChildren()),
            material_targets=[str(t) for t in p.GetRelationship('material:binding').GetTargets()]))
print(json.dumps(dict(prims=rows,errors=[str(e) for e in s.GetCompositionErrors()],
    baseline_layers=[l.identifier for l in s.GetUsedLayers() if not l.anonymous])))
'''
libs=sorted(Path('/root/isaacsim/extscache').glob('omni.usd.libs-*'))[-1]
env=dict(os.environ);env['LD_LIBRARY_PATH']=str(next(libs.rglob('libusd_tf.so')).parent)+':/root/isaacsim/kit/lib'
r=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(libs)],env=env,capture_output=True,text=True,timeout=50)
print(json.dumps(dict(exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr)));raise SystemExit(r.returncode)
