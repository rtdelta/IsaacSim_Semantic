"""Snapshot only visualizer source/assets, retaining relative gpufree-data paths."""
import hashlib,json,os,stat,tarfile,time
from pathlib import Path
root=Path('/root/gpufree-data')
work=root/'.migration_sensor_20261010_dual'
work.mkdir(mode=0o700,exist_ok=True)
marker=work/'owner.json'
owner={'task':'sensor-visualizer-dual-migration-20261010'}
if marker.exists() and json.loads(marker.read_text())!=owner:raise RuntimeError('Work directory ownership conflict')
marker.write_text(json.dumps(owner))
scopes=['IsaacSim_Asset','semantic/scripts/260920SensorVisualizer','semantic/scripts/260907LidarVisualizer','camera']
excluded={'.git','__pycache__','.venv','.venv-web','.cache','node_modules','output','outputs','incoming','deploy_history','reports','backups'}
files={};links=[]
for scope in scopes:
    base=root/scope
    if not base.is_dir():raise RuntimeError('Missing required source directory: '+scope)
    for current,dirs,names in os.walk(base,followlinks=False):
        dirs[:]=sorted(d for d in dirs if d not in excluded)
        for d in dirs:
            if (Path(current)/d).is_symlink():raise RuntimeError('Review directory symlink before migration')
        for n in sorted(names):
            p=Path(current)/n
            if p.is_symlink():raise RuntimeError('Review file symlink before migration')
            if p.name=='.env' or p.suffix in {'.mcap','.db3','.pyc','.log'}:continue
            if not p.is_file():continue
            files[str(p.relative_to(root))]=p
for name in ['performance_collected.json','performance_validation.json','native_acceptance_collected.json',
             'native_acceptance_validation.json','native_trace_analysis.json','linux_unit_tests.json','final_state.json']:
    p=root/'semantic/scripts/260920SensorVisualizer/v06/reports'/name
    if p.is_file():files[str(p.relative_to(root))]=p
rows=[];start=time.monotonic()
for name,p in sorted(files.items()):
    st=p.stat();h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
    if p.stat().st_mtime_ns!=st.st_mtime_ns:raise RuntimeError('Source changed while hashing: '+name)
    rows.append({'path':name,'size':st.st_size,'sha256':h.hexdigest(),'mtime_ns':st.st_mtime_ns,'mode':stat.S_IMODE(st.st_mode)})
manifest={'schema':1,'task':owner['task'],'source_root':str(root),'scopes':scopes,
          'excluded_directories':sorted(excluded),'files':rows,'bytes':sum(r['size'] for r in rows)}
mp=work/'migration_manifest.json';mp.write_text(json.dumps(manifest,indent=2))
partial=work/'assets_and_code.tar.gz.part';archive=work/'assets_and_code.tar.gz'
last=time.monotonic();done=0
with tarfile.open(partial,'w:gz',compresslevel=1,dereference=False) as tf:
    for row in rows:
        p=root/row['path'];st=p.stat()
        if st.st_size!=row['size'] or st.st_mtime_ns!=row['mtime_ns']:raise RuntimeError('Source changed before snapshot: '+row['path'])
        tf.add(p,arcname=row['path'],recursive=False);done+=row['size']
        if p.stat().st_mtime_ns!=row['mtime_ns']:raise RuntimeError('Source changed during snapshot: '+row['path'])
        if time.monotonic()-last>5:print(json.dumps({'phase':'archive','source_bytes_added':done}),flush=True);last=time.monotonic()
    tf.add(mp,arcname='migration_manifest.json',recursive=False)
os.replace(partial,archive)
h=hashlib.sha256()
with archive.open('rb') as f:
    for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
meta={'archive':str(archive),'archive_bytes':archive.stat().st_size,'archive_sha256':h.hexdigest(),
      'manifest_sha256':hashlib.sha256(mp.read_bytes()).hexdigest(),'files':len(rows),
      'source_bytes':manifest['bytes'],'elapsed_s':time.monotonic()-start}
(work/'archive_metadata.json').write_text(json.dumps(meta,indent=2));print(json.dumps({'phase':'prepared',**meta}),flush=True)
