"""Read final project-scoped preservation and process evidence; no Kit launch."""
import datetime,hashlib,json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
files=[{'path':str(p),'sha256':sha(p),'size_bytes':p.stat().st_size} for p in sorted(root.parent.rglob('*'))
    if p.is_file() and p.suffix in ('.py','.json','.kit','.sh') and not any(x in p.parts for x in ('single0601ContinuousRt','reports','__pycache__'))]
scene=Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda')
baseline=json.loads((root/'reports/recovery_baseline_remote.json').read_text())
ready=[]
for p in sorted(Path('/root/gpufree-data/semantic/output/single0601ContinuousRt/datasets').glob('*/READY')):
    manifest=p.parent/'dataset_manifest.json'
    ready.append({'recording_id':p.parent.name,'manifest_sha256':sha(manifest),'ready_matches':p.read_text().strip()==sha(manifest)})
kit=[]
for p in Path('/proc').iterdir():
    if not p.name.isdigit():continue
    try:
        command=(p/'cmdline').read_bytes()
        if b'/kit/kit' in command:kit.append({'pid':int(p.name),'project_owned':str(root).encode() in command})
    except (FileNotFoundError,PermissionError,ProcessLookupError):pass
report={'schema_version':1,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'scope':'Final original source/scene and root READY manifest preservation; no repeated full MCAP readback',
    'source_files':files,'scene':{'path':str(scene),'sha256':sha(scene)},'ready':ready,
    'ready_same_as_c0':ready==baseline['ready'],'scene_same_as_c0':sha(scene)==baseline['scene']['sha256'],
    'kit_processes':kit,'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=uuid,name,memory.used','--format=csv,noheader,nounits'],text=True).strip()}
(root/'reports/recovery_final_preservation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
