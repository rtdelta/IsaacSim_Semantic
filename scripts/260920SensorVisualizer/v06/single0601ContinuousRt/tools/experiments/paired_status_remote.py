import json,subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt/reports/paired_capture_experiments')
result=[]
for path in sorted(root.glob('*/repeats/*')):
    item={'directory':str(path)}
    for name in ('coordinator_status.json','continuous_terminal.json','frozen_terminal.json','analysis/summary.json','analysis/mcap_readback.json','frozen_room/phase_checkpoint.json'):
        p=path/name
        if p.exists():
            value=json.loads(p.read_text())
            if name=='coordinator_status.json':value={k:v for k,v in value.items() if k!='spec'}
            if name=='continuous_terminal.json':value={k:v for k,v in value.items() if k not in ('spec','traceback','cleanup')}
            if name=='analysis/summary.json':value={k:v for k,v in value.items() if k not in ('comparison_scope','mechanism_unresolved','image_quality_comparison')}
            if name=='analysis/mcap_readback.json':value={k:value.get(k) for k in ('passed','groups','messages','tf_matrix_max_abs_error','writer_digests_match','failure')}
            item[name]=value
    for name in ('continuous_launch.log','frozen_v06_launch.log','frozen_room_launch.log','coordinator.log','analysis_stdout.log'):
        p=path/name
        if p.exists():
            if item.get('coordinator_status.json',{}).get('state')=='FAILED' and 'e0_scene18/repeats/r01' not in str(path):
                raw=p.read_text(errors='replace');item[name+'_tail']=raw[-1200:]
    result.append(item)
batch=root.parent/'paired_batch_status.json';logs=list(root.parent.glob('paired_batch_launch*.log'))
print(json.dumps({'runs':result,'batch':json.loads(batch.read_text()) if batch.exists() else None,
    'batch_log_tail':[(p.name,p.read_text(errors='replace')[-1200:]) for p in logs],
    'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True).strip()}))
