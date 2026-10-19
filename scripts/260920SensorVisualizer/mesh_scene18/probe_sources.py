"""Read source coordinate evidence and engine availability; never edits remote data."""
import json, os, subprocess
from pathlib import Path
install=Path('/root/isaacsim')
sdk=sorted((install/'extscache').glob('omni.usd.libs-*/pxr'))[-1].parent
env=os.environ.copy()
for key in ('PYTHONHOME','PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(key,None)
env['LD_LIBRARY_PATH']=':'.join(map(str,(install/'kit/python/lib',install/'kit',sdk/'bin',sdk/'lib')))
code=r'''
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,SDK)
from pxr import Usd,UsdGeom,Sdf
root=Path('/root/gpufree-data/IsaacSim_Asset')
folder=root/'excavator_module_set/Sim_Fangshan_02'
result={'small_files':[],'files':{},'stages':{},'existing_targets':[]}
for p in folder.rglob('*'):
 if p.is_file() and p.suffix in ('.json','.md','.py') and p.stat().st_size<100000:
  result['small_files'].append(str(p.relative_to(folder)))
for name in ['combine_stage/combine_scene_17_terrain_fisheye.usda','combine_stage/combine_scene_18_terrain_fisheye_mesh.usda','excavator_module_set/Excavator_Mesh_Contract/Excavator_Mesh_Contract.usda']:
 p=root/name
 if p.exists():result['existing_targets'].append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
paths={'raw_track':root/'excavator_module_set/Excavator_3DGS_Contract/geometry/track.usdc','aligned_track':folder/'3dgs_usd/track.usd','corrected_mesh':folder/'waji_mesh_corrected.usdc'}
for key,path in paths.items():
 stage=Usd.Stage.Open(str(path));rows=[]
 for prim in stage.Traverse():
  row={'path':str(prim.GetPath()),'type':prim.GetTypeName(),'custom_data':str(prim.GetCustomData())[:8000]}
  if prim.IsA(UsdGeom.Xformable):row['local']=str(UsdGeom.Xformable(prim).GetLocalTransformation())
  row['attributes']=[]
  for a in prim.GetAttributes():
   if a.HasAuthoredValueOpinion():
    v=a.Get();n=len(v) if hasattr(v,'__len__') else None
    small=str(v) if n is None or n<17 else str(v[:2])
    row['attributes'].append({'name':a.GetName(),'type':str(a.GetTypeName()),'length':n,'value':small[:1200]})
  row['relationships']={r.GetName():[str(t) for t in r.GetTargets()] for r in prim.GetRelationships() if r.HasAuthoredTargets()}
  rows.append(row)
 result['stages'][key]={'metadata':str(stage.GetRootLayer().customLayerData)[:10000],'rows':rows}
print(json.dumps(result))
'''.replace('SDK',repr(str(sdk)))
p=subprocess.run([str(install/'kit/python/bin/python3'),'-I','-S','-B','-'],input=code,env=env,capture_output=True,text=True,timeout=65)
result={'returncode':p.returncode,'stderr':p.stderr[-4000:],'data':json.loads(p.stdout) if p.returncode==0 else p.stdout[-4000:]}
result['kit_processes']=[]
for proc in Path('/proc').iterdir():
 if not proc.name.isdigit():continue
 try:
  comm=(proc/'comm').read_text().strip()
  if comm in ('kit','isaac-sim'):
   result['kit_processes'].append({'pid':proc.name,'cmd':(proc/'cmdline').read_bytes().replace(b'\x00',b' ').decode()[:1800]})
 except (OSError,PermissionError):pass
gpu=subprocess.run(['nvidia-smi','--query-gpu=name,memory.used,memory.total,utilization.gpu','--format=csv,noheader'],capture_output=True,text=True,timeout=15)
result['gpu']=gpu.stdout
print(json.dumps(result))
