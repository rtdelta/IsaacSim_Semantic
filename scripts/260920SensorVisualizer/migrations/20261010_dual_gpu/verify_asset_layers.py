"""Read local USD layers with the installed SDK, without composing a Stage."""
import json, os, subprocess
from pathlib import Path
work=Path('/root/gpufree-data/.migration_sensor_20261010_dual')
assert json.loads((work/'owner.json').read_text())['task']=='sensor-visualizer-dual-migration-20261010'
install=Path('/root/isaacsim')
libs=list((install/'extscache').glob('omni.usd.libs-*/pxr'))
assert len(libs)==1
sdk=libs[0].parent
env=os.environ.copy()
for name in ('PYTHONHOME','PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(name,None)
env['LD_LIBRARY_PATH']=':'.join(map(str,(install/'kit/python/lib',install/'kit',sdk/'bin',sdk/'lib')))
code='''import sys,json,posixpath,zipfile
from pathlib import Path
sys.path.insert(0,SDK)
from pxr import Sdf,UsdUtils
root=Path('/root/gpufree-data')
pending=[root/'IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda']
seen=set();layers=[];missing=[];external=[];packages=[];installed_mdl=[]
while pending:
    p=pending.pop().resolve()
    if str(p) in seen:continue
    seen.add(str(p))
    if len(seen)>300:raise RuntimeError('Unexpectedly large dependency graph')
    if not p.is_relative_to(root):raise RuntimeError('Dependency outside migration scope: '+str(p))
    if not p.is_file():missing.append(str(p));continue
    layer=Sdf.Layer.FindOrOpen(str(p))
    if layer is None:raise RuntimeError('Cannot read USD layer: '+str(p))
    dependencies=list(layer.GetExternalReferences())
    assets=[]
    def values(v):
        if isinstance(v,Sdf.AssetPath):assets.append(v.path)
        elif isinstance(v,dict):
            for x in v.values():values(x)
        elif isinstance(v,(list,tuple)) or type(v).__name__=='AssetPathArray':
            for x in v:values(x)
    def visit(path):
        spec=layer.GetObjectAtPath(path)
        if isinstance(spec,Sdf.AttributeSpec) and str(spec.typeName) in ('asset','asset[]'):
            for key in ('default','timeSamples'):
                if spec.HasInfo(key):values(spec.GetInfo(key))
    layer.Traverse('/',visit)
    row={'path':str(p),'references':dependencies,'asset_paths':list(dict.fromkeys(assets))}
    layers.append(row)
    for ref in list(dict.fromkeys(dependencies+assets)):
        if not ref:continue
        if '://' in ref:external.append({'layer':str(p),'reference':ref});continue
        if p.suffix.lower()=='.usdz' and '[' not in ref:
            with zipfile.ZipFile(p) as z:
                names=set(z.namelist())
                member=posixpath.normpath(ref)
                exists=member in names
            packages.append({'layer':str(p),'reference':ref,'member_exists':exists,
                             'checked':'local zip member name; nested layers not composed'})
            if not exists:missing.append(str(p)+'['+member+']')
            continue
        if '[' in ref:
            packages.append({'layer':str(p),'reference':ref,'checked':'package expression not expanded'});continue
        q=Path(ref);q=(q if q.is_absolute() else p.parent/q).resolve()
        if not q.is_relative_to(root):missing.append(str(q));continue
        if not q.is_file():
            if q.suffix=='.mdl' and Path(ref).name==ref:
                candidates=list(Path('/root/isaacsim/kit').rglob(ref))
                if candidates:
                    installed_mdl.append({'reference':ref,'installed_candidates':[str(x) for x in candidates]})
                    continue
            missing.append(str(q));continue
        if q.suffix.lower() in ('.usd','.usda','.usdc','.usdz'):pending.append(q)
print(json.dumps({'layers':layers,'layer_count':len(layers),'missing':sorted(set(missing)),
                  'external_urls':external,'package_references':packages,'installed_mdl':installed_mdl,
                  'mode':'Sdf local layers only; no Stage composition or Kit rendering'}))
'''.replace('SDK',repr(str(sdk)))
p=subprocess.run([str(install/'kit/python/bin/python3'),'-I','-S','-B','-'],input=code,env=env,capture_output=True,text=True,timeout=45)
report={'exit_code':p.returncode,'stderr':p.stderr[-3000:]}
if p.returncode==0:report['probe']=json.loads(p.stdout)
else:report['stdout']=p.stdout[-2000:]
(work/'asset_layer_validation.json').write_text(json.dumps(report,indent=2))
small={'exit_code':report['exit_code'],'stderr':report['stderr']}
if p.returncode==0:
    small.update({k:v for k,v in report['probe'].items() if k!='layers'})
print(json.dumps(small))
