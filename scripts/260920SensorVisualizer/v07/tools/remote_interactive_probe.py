"""Read recent real owner timing; rolling windows are explicitly labelled."""
import json
from pathlib import Path
import sys
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v07');sys.path.insert(0,str(root))
from sensor_visualizer_v07.control_ipc import request
report=json.loads((root/'reports/native_validation_status.json').read_text())
directory=Path(report['directory'])/'v07'
state=request(directory/'runtime/engine.sock',{'action':'status'},timeout=2)
if 'statistics' not in state:
    print(json.dumps({'phase':report['phase'],'owner_state':{k:v for k,v in state.items() if k!='receipts'},
                      'recent_receipts':state.get('receipts',[])[-3:]}));raise SystemExit(0)
def distribution(values):
    values=sorted(values)
    return {'count':len(values),'p50_ms':values[len(values)//2],'p95_ms':values[min(len(values)-1,int(len(values)*.95))],
            'p99_ms':values[min(len(values)-1,int(len(values)*.99))],'max_ms':values[-1]} if values else {'count':0}
stats=state['statistics']
keys=[(r['completed_ns']-r['accepted_ns'])/1e6 for r in state['receipts'] if r.get('action')=='keys' and r.get('accepted_ns')]
print(json.dumps({'phase':report['phase'],'source':'recent rolling windows, not whole-run percentiles',
                  'owner_processing':distribution(stats['owner_ms_samples']),
                  'owner_update_gap':distribution(stats['frame_gap_samples']),
                  'key_receipt':distribution(keys),'keyboard':state['input_status'],
                  'native_gpu_renderer':state.get('metadata',{}).get('render',{}).get('renderer'),
                  'playing':state['playing'],'control_time_s':state['state']['t_sim_s']}))
