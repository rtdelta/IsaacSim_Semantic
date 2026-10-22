"""Bounded copy of task-created immutable reports and raw probe evidence for SFTP."""
import hashlib
import json
from pathlib import Path
import shutil
import time
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
output=Path('/root/gpufree-data/semantic/output/single0601ContinuousRt')
destination=root/'reports'/('delivery_evidence_'+time.strftime('%Y%m%d_%H%M%S'))
destination.mkdir(exist_ok=False)
items=[]
limit=128*1024*1024
used=0
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def copy(source,relative):
    global used
    size=source.stat().st_size
    if size>2*1024*1024 or used+size>limit:
        items.append({'source':str(source),'path':relative,'sha256':sha(source),'size_bytes':size,
                      'copied':False,'reason':'Explicit bounded evidence export; full original remains in remote recording'})
        return
    target=destination/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
    actual=sha(target)
    if actual!=sha(source):
        raise RuntimeError('Copied evidence SHA differs')
    items.append({'source':str(source),'path':relative,'sha256':actual,'size_bytes':size,'copied':True})
    used+=size
names=('session.json','readback_session_input.json','job_spec.json','capabilities.json','environment.json','asset_manifest.json',
       'source_manifest.json','sensor_registry.json','render_profile.json','performance.json','validation.json','dataset_manifest.json',
       'READY','worker_report.json','lifecycle.json','diagnostic_geometry.json','geometry_diagnostics.json','logs/engine_error.log','logs/worker_stderr.log')
summary=[]
for path in sorted(output.glob('*/*/session.json')):
    directory=path.parent
    session=json.loads(path.read_text())
    if session['outcome'] is None:
        continue
    for name in names:
        if (directory/name).is_file():
            copy(directory/name,'recordings/'+directory.name+'/'+name)
    for name in ('capability_probe/receipts.json','capability_probe/errors.json'):
        if (directory/name).is_file():copy(directory/name,'recordings/'+directory.name+'/'+name)
    summary.append({'recording_id':directory.name,'remote_directory':str(directory),'status':session['status'],'counts':session['counts'],
                    'acceptance_results':session['acceptance_results'],'failure':session.get('failure')})
for directory in sorted((root/'reports').glob('*probe_*')):
    if directory.is_dir():
        for path in directory.rglob('*'):
            if path.is_file() and path.stat().st_size<=10*1024*1024:
                copy(path,'probes/'+directory.name+'/'+path.relative_to(directory).as_posix())
for directory in (root/'reports').glob('matrix_*'):
    if (directory/'results.json').is_file():copy(directory/'results.json','matrices/'+directory.name+'/results.json')
(destination/'evidence_manifest.json').write_text(json.dumps({'schema_version':1,'files':items,'bytes':used,'recordings':summary},indent=2)+'\n')
print(json.dumps({'relative_path':destination.relative_to(root).as_posix(),'files':len(items),'bytes':used,'recordings':len(summary),
                  'omitted_large_files':sum(not f['copied'] for f in items)}))
