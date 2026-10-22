"""Read just the owned validation state, current log and physical GPU load."""
import json
import subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v07')
status=json.loads((root/'reports/native_validation_status.json').read_text())
out={key:status.get(key) for key in ('state','phase','directory','error','active_task','worker_prepare_s')}
out['cases']=[{key:row.get(key) for key in ('case','state','groups','total_wall_s','wall_s','session')}
              for row in status.get('results',[])]
directory=Path(status['directory'])/'v07'
worker=directory/'runtime/capture_worker_status.json'
if worker.exists():out['worker']=json.loads(worker.read_text())
current=directory/'runtime/capture_service.log' if worker.exists() else directory/'kit.log'
if current.exists():
    with current.open('rb') as stream:
        stream.seek(max(0,current.stat().st_size-2000));out['log_tail']=stream.read().decode('utf-8','replace')
out['gpus']=subprocess.run(['nvidia-smi','--query-gpu=index,uuid,utilization.gpu,memory.used',
                           '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=10).stdout
print(json.dumps(out))
