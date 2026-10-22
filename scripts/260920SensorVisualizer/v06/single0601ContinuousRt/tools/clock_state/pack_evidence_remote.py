"""Lossless compact metadata/analysis collection; full native payloads stay in place."""
import datetime,hashlib,io,json,tarfile
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
source=root/'reports/clock_state_consistency'
destination=root/'reports/clock_state_delivery_20261014.tar.gz'
if destination.exists():raise RuntimeError('Refuse evidence pack overwrite; choose a distinct delivery revision')
copied=[];total=0;paths=[]
exclude={'sensor_registry.json','gmo_headers.json'}
for p in sorted(source.rglob('*')):
    rel=p.relative_to(source)
    if p.is_symlink():raise RuntimeError('Refuse symbolic link in evidence pack: '+str(rel))
    if not p.is_file() or any(s in rel.parts for s in ('payloads','trace_samples')) or p.suffix not in ('.json','.jsonl'):continue
    if p.name in exclude:continue
    if p.stat().st_size>64*1024**2:raise RuntimeError('Unexpected metadata file size')
    data=p.read_bytes();total+=len(data)
    if total>2*1024**3:raise RuntimeError('Uncompressed delivery metadata budget; original evidence retained')
    paths.append((p,rel))
    copied.append({'path':rel.as_posix(),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
manifest=json.dumps({'schema_version':1,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'source_root':str(source),'scope':'all compact JSON/JSONL metadata and analysis, phase traces, raw-event metadata and original file manifests; complete native payloads retained remotely',
    'excluded_names':sorted(exclude),'files':copied,'bytes':total},indent=2).encode('utf-8')
with destination.open('xb') as file:
    with tarfile.open(fileobj=file,mode='w:gz',compresslevel=6) as archive:
        for p,rel in paths:archive.add(p,arcname=rel.as_posix(),recursive=False)
        info=tarfile.TarInfo('delivery_manifest.json');info.size=len(manifest);archive.addfile(info,io.BytesIO(manifest))
if destination.stat().st_size>240*1024**2:raise RuntimeError('Compressed delivery budget; retained archive, split before transfer')
print(json.dumps({'archive':str(destination),'files':len(copied),'uncompressed_bytes':total,'archive_bytes':destination.stat().st_size,
    'archive_sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}))
