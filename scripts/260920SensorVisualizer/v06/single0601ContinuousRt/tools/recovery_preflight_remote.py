"""Freeze C0 evidence and inspect installed native interfaces; no engine launch."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

root = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
install = Path('/root/isaacsim')
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
kit = []
for proc in Path('/proc').iterdir():
    if proc.name.isdigit():
        try:
            args = (proc/'cmdline').read_bytes()
            if b'/kit/kit' in args:
                kit.append({'pid':int(proc.name),'belongs_to_project':str(root).encode() in args})
        except (FileNotFoundError,PermissionError,ProcessLookupError):
            pass
files = [{'path':p.relative_to(root).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size}
         for p in sorted(root.rglob('*')) if p.is_file() and p.suffix in ('.py','.json','.md','.kit','.sh')
         and not any(x in p.parts for x in ('reports','.deploy_backups','__pycache__'))]
scene = Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda')
ready = []
for p in sorted(Path('/root/gpufree-data/semantic/output/single0601ContinuousRt/datasets').glob('*/READY')):
    manifest = p.parent/'dataset_manifest.json'
    ready.append({'recording_id':p.parent.name,'manifest_sha256':sha(manifest),'ready_matches':p.read_text().strip()==sha(manifest)})
report = {'schema_version':1,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'scope':'C0 source/asset freeze; READY manifests only, not repeated full MCAP validation',
          'kit_processes':kit,'files':files,'scene':{'path':str(scene),'sha256':sha(scene)},'ready':ready,
          'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=uuid,name,driver_version,memory.total,memory.used','--format=csv,noheader,nounits'],text=True).strip()}
target = root/'reports/recovery_baseline_remote.json'
target.write_text(json.dumps(report,indent=2))
sdk = []
needles = ('def parse_generic_model_output_data','class GenericModelOutput','GenericModelOutput"','GenericModelOutput\'',
           'get_world_poses','def register_callback','PHYSICS_POST_STEP','PHYSICS_PRE_STEP')
tops = [install/'exts/isaacsim.sensors.experimental.rtx',install/'exts/isaacsim.sensors.rtx.nodes',
        install/'exts/isaacsim.core.experimental.prims',install/'exts/isaacsim.core.simulation_manager',
        install/'exts/isaacsim.core.rendering_manager']
for top in tops:
    for p in top.rglob('*.py'):
        if 'tests' in p.parts or p.stat().st_size>400000:
            continue
        data = p.read_text(errors='replace')
        lines = data.splitlines(); selected = set()
        for i,line in enumerate(lines):
            if any(word in line for word in needles):
                selected.update(range(max(0,i-3),min(len(lines),i+50)))
        if selected:
            sdk.append({'path':str(p),'sha256':sha(p),'lines':[{'line':i+1,'text':lines[i]} for i in sorted(selected)][:180]})
print(json.dumps({'baseline':{'path':str(target),'source_files':len(files),'ready_count':len(ready),
                'ready_manifest_all_match':all(x['ready_matches'] for x in ready),'kit_processes':kit,'scene':report['scene'],'gpu':report['gpu']},'sdk':sdk}))
