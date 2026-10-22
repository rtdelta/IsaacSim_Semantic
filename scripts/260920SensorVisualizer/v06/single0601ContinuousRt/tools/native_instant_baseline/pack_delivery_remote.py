"""Collect verified compact metadata; all raw payloads remain at original paths."""
import datetime,hashlib,io,json,tarfile
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
source=root/'reports/native_instant_baseline';destination=root/'reports/native005_delivery_20261015.tar.gz'
order=json.loads((root/'config/native_instant_baseline/run_order.json').read_text())
status=json.loads((source/order['experiment_id']/'sequence_status.json').read_text())
if status['state'] not in ('COMPLETE','FAILED'):raise RuntimeError('Do not snapshot a running sequence')
if destination.exists():raise RuntimeError('Refuse delivery overwrite')
paths=[];entries=[];total=0;exclude={'sensor_registry.json','sensor_manifest.json','gmo_headers.json'}
for p in sorted(source.rglob('*')):
    if p.is_symlink():raise RuntimeError('Evidence symlink')
    rel=p.relative_to(source)
    if not p.is_file() or p.suffix not in ('.json','.jsonl') or p.name in exclude or any(x in rel.parts for x in ('payloads','gmo','trace_samples')):continue
    data=p.read_bytes();total+=len(data)
    if len(data)>64*1024**2 or total>2*1024**3:raise RuntimeError('Metadata delivery budget')
    paths.append((p,rel));entries.append({'path':rel.as_posix(),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
for p in sorted((root/'config/native_instant_baseline').rglob('*.json')):
    rel=Path('frozen_config')/p.relative_to(root/'config/native_instant_baseline');data=p.read_bytes();total+=len(data)
    paths.append((p,rel));entries.append({'path':rel.as_posix(),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
manifest={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_root':str(source),'scope':'All compact metadata/analysis, including discarded qualifications. Full XYZ/GMO and large sensor arrays remain remote, covered by original file manifests.',
    'excluded_names':sorted(exclude),'files':entries,'uncompressed_bytes':total,'sequence_state':status['state']}
with destination.open('xb') as f:
    with tarfile.open(fileobj=f,mode='w:gz',compresslevel=6) as z:
        for p,rel in paths:z.add(p,arcname=rel.as_posix(),recursive=False)
        data=json.dumps(manifest,indent=2).encode();info=tarfile.TarInfo('delivery_manifest.json');info.size=len(data);z.addfile(info,io.BytesIO(data))
if destination.stat().st_size>240*1024**2:raise RuntimeError('Split archive before transfer')
print(json.dumps({'archive':str(destination.relative_to(root)),'archive_bytes':destination.stat().st_size,'archive_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'files':len(entries),'uncompressed_bytes':total}))
