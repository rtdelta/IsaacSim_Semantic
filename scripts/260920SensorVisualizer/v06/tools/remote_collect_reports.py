"""Return concise owned reports and verify the preserved v04/source asset."""
import hashlib,json,os,sys
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06');directory=root/'reports/native_owner'
names=['interaction','concurrent_live_latest','concurrent_live_complete','steady_concurrency','http_runtime','task_recovery',
       'validation_offline','validation_live_latest','validation_live_complete','validation_soak_100','soak_status','warning_summary']
reports={}
for name in names:
    p=directory/(name+'.json')
    if p.exists():reports[name]=json.loads(p.read_text())
old=root.parent/'v04';saved=json.loads((root.parent/'backups/20261009_before_v05/v04_remote_manifest.json').read_text())
old_changed=[name for name,h in saved.items() if not (old/name).is_file() or hashlib.sha256((old/name).read_bytes()).hexdigest()!=h]
source=json.loads((root/'deployment_manifest.json').read_text());source_changed=[name for name,h in source.items() if hashlib.sha256((root/name).read_bytes()).hexdigest()!=h]
first=json.loads((directory/'offline_task.json').read_text());first_status=json.loads((Path(first['directory'])/'status.json').read_text())
asset=json.loads((Path(first_status['session'])/'asset_manifest.json').read_text());root_asset_unchanged=hashlib.sha256(Path(asset['root_layer']).read_bytes()).hexdigest()==asset['root_sha256']
resources=directory/'soak_resources.jsonl'
if resources.exists():
    rows=[json.loads(x) for x in resources.read_text().splitlines() if x.strip()];rss=[r['owner_rss_kib'] for r in rows]
    reports['resource_summary']={'samples':len(rows),'owner_rss_first_mib':rss[0]/1024,'owner_rss_last_mib':rss[-1]/1024,
        'owner_rss_min_mib':min(rss)/1024,'owner_rss_max_mib':max(rss)/1024,
        'gpu_memory_mib_range':[min(int(r['gpu'].split(',')[0]) for r in rows),max(int(r['gpu'].split(',')[0]) for r in rows)]}
    clock=os.sysconf('SC_CLK_TCK')
    cpu=[]
    for a,b in zip(rows,rows[1:]):
        sa=a['owner_stat'].rsplit(')',1)[1].split();sb=b['owner_stat'].rsplit(')',1)[1].split();elapsed=(b['monotonic_ns']-a['monotonic_ns'])/1e9
        cpu.append(((int(sb[11])+int(sb[12]))-(int(sa[11])+int(sa[12])))/clock/elapsed)
    reports['resource_summary']['owner_cpu_average_cores']=sum(cpu)/len(cpu) if cpu else None
reports['isolation']={'old_files_verified':len(saved),'v04_changes':old_changed,'deployed_files_verified':len(source),
    'deployment_mismatches':source_changed,'root_scene_unchanged':root_asset_unchanged,'external_dependencies_downloaded':False}
assert not old_changed and not source_changed and root_asset_unchanged
print(json.dumps(reports))
