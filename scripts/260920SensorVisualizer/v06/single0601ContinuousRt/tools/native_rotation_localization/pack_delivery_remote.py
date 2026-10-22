"""Terminal metadata snapshot with explicit hashes; raw arrays remain preserved remotely."""
import datetime,hashlib,io,json,shutil,tarfile
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt');source=root/'reports/native_rotation_localization/native007_20261015_v1'
destination=root/'reports/native007_delivery_20261015.tar.gz'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for p in (source/'sequences').glob('*/status.json'):
 if json.loads(p.read_text())['state']=='running':raise RuntimeError('Cannot snapshot running sequence')
for name in ('declared_followup','stage2_followup'):
 pipeline=source/name/'status.json'
 if pipeline.is_file() and json.loads(pipeline.read_text())['state']=='running':raise RuntimeError('Pipeline running')
if destination.exists():raise RuntimeError('Refuse delivery overwrite')
locks={}
for folder in ('native_instant_baseline','native_rotation_localization/v1'):
 lock=json.loads((root/'config'/folder/'main_code_lock.json').read_text());bad=[r['path'] for r in lock['files'] if sha(root/r['path'])!=r['sha256']]
 locks[folder]={'files':len(lock['files']),'mismatches':bad}
 if bad:raise RuntimeError('Frozen source changed')
asset=Path('/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda')
if sha(asset)!='e44ff38c21caaaccf20aa44a9b834e33d7109407e737df27198a63ad95e9fb79':raise RuntimeError('Original scene changed')
inventory={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'locks':locks,'original_scene_sha256':sha(asset),'free_bytes':shutil.disk_usage(root).free,'runs':[]}
for p in sorted(source.glob('*/*/*/*/analysis/summary.json')):
 parent=p.parent.parent;final=parent/'analysis_final/summary.json';s=json.loads((final if final.is_file() else p).read_text());m=json.loads((parent/'continuous/file_manifest.json').read_text())
 inventory['runs'].append({'path':parent.relative_to(source).as_posix(),'analysis':str((final if final.is_file() else p).relative_to(source)),
  'targets':s['planned_targets'],'raw_events':s['raw_events'],'decoded':s['readback']['full_GMO_independently_decoded'],'measurement_qualified':s['measurement_qualified'],
  'evidence_bytes':sum(r['bytes'] for r in m['files']),'evidence_files':len(m['files']),'queue_peak_bytes':m['queue_peak_bytes'],'reserved_disk_bytes':m['reserved_disk_bytes'],'cleanup_ok':s['cleanup_ok']})
inventory['partial_runs']=[]
for p in sorted(source.glob('*/*/*/*/warmup_semantics_analysis.json')):
 parent=p.parent;s=json.loads(p.read_text());m=json.loads((parent/'continuous/file_manifest.json').read_text())
 inventory['partial_runs'].append({'path':parent.relative_to(source).as_posix(),'targets':s['captured_target_count'],'planned_targets':s['planned_targets'],'raw_events':s['preserved_warmup_events'],'decoded':s['full_GMO_decoded'],
 'evidence_bytes':sum(r['bytes'] for r in m['files']),'evidence_files':len(m['files']),'queue_peak_bytes':m['queue_peak_bytes'],'reserved_disk_bytes':m['reserved_disk_bytes'],'cleanup_ok':s['cleanup']['passed']})
inventory['all_preserved_targets']=sum(r['targets'] for r in inventory['runs']);inventory['all_preserved_raw_events']=sum(r['raw_events'] for r in inventory['runs'])
inventory['all_preserved_raw_events']+=sum(r['raw_events'] for r in inventory['partial_runs'])
inventory['all_raw_readback_complete']=all(r['raw_events']==r['decoded'] for r in inventory['runs']+inventory['partial_runs'])
inventory['remaining_capture_processes']=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  cmd=(p/'cmdline').read_bytes()
  if b'/kit/kit' in cmd or (str(root).encode() in cmd and b'--worker' in cmd):inventory['remaining_capture_processes'].append(int(p.name))
 except OSError:pass
if inventory['remaining_capture_processes']:raise RuntimeError('Owned capture or Kit still present')
inventory['formal_continuous_acceptance']=False
(source/'final_inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
paths=[];entries=[];total=0
for base,prefix in ((source,Path('evidence')),(root/'config/native_rotation_localization',Path('frozen_config')),(root/'tools/native_rotation_localization',Path('implementation'))):
 for p in sorted(base.rglob('*')):
  if p.is_symlink():raise RuntimeError('Evidence symlink')
  if not p.is_file() or p.suffix not in ('.json','.jsonl','.md','.py'):continue
  rel=prefix/p.relative_to(base);data=p.read_bytes();total+=len(data)
  if len(data)>64*1024**2 or total>2*1024**3:raise RuntimeError('Metadata budget')
  paths.append((p,rel));entries.append({'path':rel.as_posix(),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
manifest={'utc':inventory['utc'],'source_root':str(source),'scope':'All JSON/JSONL metadata and analyses, frozen configs and implementation; raw XYZ/GMO preserved remotely under file manifests.',
 'files':entries,'uncompressed_bytes':total,'formal_continuous_acceptance':False}
with destination.open('xb') as f:
 with tarfile.open(fileobj=f,mode='w:gz',compresslevel=6) as z:
  for p,rel in paths:z.add(p,arcname=rel.as_posix(),recursive=False)
  data=json.dumps(manifest,indent=2).encode();info=tarfile.TarInfo('delivery_manifest.json');info.size=len(data);z.addfile(info,io.BytesIO(data))
if destination.stat().st_size>240*1024**2:raise RuntimeError('Split archive before transfer')
print(json.dumps({'archive':str(destination.relative_to(root)),'archive_bytes':destination.stat().st_size,'archive_sha256':sha(destination),'files':len(entries),'uncompressed_bytes':total,'inventory':{k:v for k,v in inventory.items() if k!='runs'}}))
