"""Decode every benchmark message; use the installed ROS runtime only."""
import json,os,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06');results={};profiles=[];registries=[];asset_hashes=[]
for label in ('baseline','motion','optimized','scheduled','diagnostic','keepalive','final'):
    pointer=root/'reports'/(label+'_performance_suite.json')
    if not pointer.exists():continue
    track=json.loads(pointer.read_text());out=Path(track['directory']);result=out/'result.json'
    if not result.exists() or not json.loads(result.read_text()).get('passed'):continue
    results[label]={}
    for case in ('concurrent','capture_only'):
        status=json.loads((out/(case+'_status.json')).read_text());session=Path(status['session'])
        env=os.environ.copy()
        for key in ('PYTHONHOME','PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(key,None)
        p=subprocess.run(['/bin/bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 -u "$@"','sv06-validate',str(root/'tools/validate_capture_data.py'),str(session)],env=env,capture_output=True,text=True,timeout=180)
        if p.returncode:raise RuntimeError(p.stdout[-1000:]+p.stderr[-4000:])
        results[label][case]=json.loads(p.stdout.split('VALIDATION_JSON=')[-1]);job=json.loads((session/'job_spec.json').read_text())
        profiles.append(job['render'])
        registry=json.loads((session/'sensor_registry.json').read_text());registries.append(registry)
        asset_hashes.append(results[label][case]['root_sha256'])
assert all(x==profiles[0] for x in profiles),'Formal render settings changed across comparison'
assert all(x==registries[0] for x in registries),'Sensor settings or calibration changed across comparison'
assert len(set(asset_hashes))==1,'Scene changed across comparison'
saved=json.loads((root/'baseline_manifest.json').read_text());import hashlib
old=root.parent/'v05';manifest=saved['sha256']
changes=[n for n,h in manifest.items() if hashlib.sha256((old/n).read_bytes()).hexdigest()!=h]
results['isolation']={'v05_files':len(manifest),'v05_changes':changes,'formal_render_profiles_identical':True,
    'sensor_registries_identical':True,'root_usd_sha256':asset_hashes[0]};assert not changes
(root/'reports/performance_validation.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results))
