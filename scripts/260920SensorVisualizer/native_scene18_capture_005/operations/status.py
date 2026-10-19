"""Read only this capture's bounded progress and diagnostics."""
import json,shutil
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_scene18_capture_005')
latest=root/'reports/latest.json'
if not latest.exists():
    print(json.dumps({'started':False}));raise SystemExit(0)
info=json.loads(latest.read_text());base=Path(info['directory']);result={'started':True,'info':info,'free_gib':shutil.disk_usage(base).free/1024**3}
for name in ('smoke','production'):
    out=base/name/'capture';row={'exists':out.exists()}
    if not out.exists():result[name]=row;continue
    for file in ('result.json','engine_result.json','engine_error.json','validation.json','group_validation.json'):
        if not (out/file).exists():continue
        data=json.loads((out/file).read_text())
        row[file]={k:data.get(k) for k in ('state','ok','frames','wall_s','process_wall_s','engine_exit','recorder_exit','validation_exit','group_validation_exit','error','errors','root_usd_unchanged','source_dependencies_unchanged') if k in data}
    groups=out/'groups.jsonl'
    if groups.exists():
        lines=groups.read_text().splitlines();row['completed_groups']=len(lines)
        if lines:
            g=json.loads(lines[-1]);row['latest_group']={k:g.get(k) for k in ('group','logical_time_s','native_time_s','payload_observed_scope_s','root_target_max_abs_error','joint_target_max_abs_error_rad')}
    events=out/'engine_events.jsonl'
    if events.exists():row['recent_events']=[json.loads(x) for x in events.read_text().splitlines()[-3:]]
    log=out/'engine.log'
    if log.exists():
        lines=log.read_text(errors='replace').splitlines();row['warning_count']=sum('[Warning]' in x for x in lines);row['error_count']=sum('[Error]' in x for x in lines)
        row['log_tail']=lines[-5:]
    row['mcap_bytes']=sum(p.stat().st_size for p in (out/'bag').glob('*.mcap'))
    if (out/'kit.pid').exists():row['kit_pid']=int((out/'kit.pid').read_text());row['kit_alive']=Path('/proc/'+str(row['kit_pid'])).exists()
    result[name]=row
delivery=base/'delivery_status.json'
if delivery.exists():result['delivery']=json.loads(delivery.read_text())
print(json.dumps(result))
