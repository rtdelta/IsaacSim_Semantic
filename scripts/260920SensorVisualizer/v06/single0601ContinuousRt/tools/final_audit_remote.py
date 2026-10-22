"""Final CPU audit of ended records and original disk asset/source hashes."""
import hashlib,json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
out=Path('/root/gpufree-data/semantic/output/single0601ContinuousRt')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
original=root.parent
files=[{'path':str(p),'sha256':sha(p),'size_bytes':p.stat().st_size} for p in sorted(original.rglob('*'))
       if p.is_file() and p.suffix in ('.py','.json','.kit','.sh') and not any(x in p.parts for x in ('single0601ContinuousRt','reports','__pycache__'))]
scene=Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda')
(root/'reports/final_original_asset_source.json').write_text(json.dumps({'schema_version':1,'scene':{'path':str(scene),'sha256':sha(scene),'size_bytes':scene.stat().st_size},'source_files':files},indent=2))
log=root/'reports/final_acceptance_audit.log'
with log.open('wb') as f:
    result=subprocess.run(['/usr/bin/python3','-B',str(root/'tools/run_acceptance.py'),str(out),'--output',str(root/'reports/acceptance_final.json')],cwd=root,stdout=f,stderr=subprocess.STDOUT,timeout=35)
report=json.loads((root/'reports/acceptance_final.json').read_text())
compact={k:report[k] for k in ('milestones','accepted_recordings','accepted_groups','all_ready_integrity_ok','full_project_accepted')}
compact['audit_exit_code']=result.returncode
compact['scene_sha256']=sha(scene)
print(json.dumps(compact))
