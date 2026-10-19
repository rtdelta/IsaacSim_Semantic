"""Read-only identity, resource and preservation baseline for clock experiments."""
import datetime,hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
files=[{'path':str(p),'sha256':sha(p),'size_bytes':p.stat().st_size} for p in sorted(ROOT.parent.rglob('*'))
    if p.is_file() and p.suffix in ('.py','.json','.kit','.sh') and not any(x in p.parts for x in ('single0601ContinuousRt','reports','__pycache__'))]
scene=Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda')
ready=[]
for p in sorted(Path('/root/gpufree-data/semantic/output/single0601ContinuousRt/datasets').glob('*/READY')):
    h=sha(p.parent/'dataset_manifest.json');ready.append({'recording_id':p.parent.name,'manifest_sha256':h,'ready_matches':p.read_text().strip()==h})
processes=[]
for p in Path('/proc').iterdir():
    if not p.name.isdigit():continue
    try:
        c=(p/'cmdline').read_bytes()
        if b'/kit/kit' in c or (str(ROOT).encode() in c and (b'--worker' in c or b'start_batch' in c)):
            processes.append({'pid':int(p.name),'command':c.decode(errors='replace').replace('\0',' ')})
    except (OSError,ProcessLookupError):pass
previous=json.loads((ROOT/'reports/paired_final_preservation_20261014_v2.json').read_text())
print(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'processes':processes,
    'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=uuid,name,memory.used','--format=csv,noheader,nounits'],text=True).strip(),
    'disk_free_bytes':shutil.disk_usage(ROOT).free,'meminfo':Path('/proc/meminfo').read_text(),
    'source_files':files,'scene_sha256':sha(scene),'ready':ready,'ready_count':len(ready),
    'source_unchanged':files==previous['source_files'],'scene_unchanged':sha(scene)==previous['scene']['sha256'],
    'ready_unchanged':ready==previous['ready']}))
