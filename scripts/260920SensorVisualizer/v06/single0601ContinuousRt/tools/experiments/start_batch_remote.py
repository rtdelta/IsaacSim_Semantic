"""Current bounded experiment batch only; no recurring scheduling."""
import json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
sys.path.insert(0,str(ROOT))
from tools.experiments.storage import save
from tools.experiments.start_paired_remote import kits
batch=ROOT/os.environ.get('S0601_BATCH_SPEC','config/experiments/e1_scene18_batch.json')
if '--worker' in sys.argv:
    states=[]
    for relative in json.loads(batch.read_text())['specs']:
        path=ROOT/relative.replace('\\','/');spec=json.loads(path.read_text());parent=ROOT/'reports/paired_capture_experiments'/spec['experiment_id']/'repeats'/spec['repeat']
        result=subprocess.run(['/usr/bin/python3','-B',str(ROOT/'tools/experiments/start_paired_remote.py'),'--spec',str(path)],capture_output=True,text=True)
        if result.returncode:raise RuntimeError(result.stderr[-3000:])
        states.append({'spec':relative,'launch':json.loads(result.stdout),'state':'running'});save(ROOT/'reports/paired_batch_status.json',{'cases':states})
        deadline=time.monotonic()+spec['wall_timeout_s']+spec['frozen_timeout_s']+300
        while time.monotonic()<deadline:
            p=parent/'coordinator_status.json'
            status=json.loads(p.read_text()) if p.exists() else {}
            if status.get('state') in ('COMPLETE','FAILED'):
                states[-1]['state']=status['state'];save(ROOT/'reports/paired_batch_status.json',{'cases':states});break
            time.sleep(2)
        else:raise RuntimeError('Batch case wall deadline')
        if states[-1]['state']=='FAILED':break
else:
    if kits():raise RuntimeError('Kit competition; batch refused')
    batch_specs=json.loads(batch.read_text())['specs'];first=json.loads((ROOT/batch_specs[0]).read_text())
    parent=ROOT/'reports/paired_capture_experiments'/first['experiment_id']
    if parent.exists():raise RuntimeError('Batch evidence exists')
    env=os.environ.copy()
    for key in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(key,None)
    log_path=ROOT/('reports/paired_batch_launch_'+time.strftime('%Y%m%d_%H%M%S')+'.log')
    with log_path.open('xb') as log:
        child=subprocess.Popen(['/usr/bin/python3','-B',str(ROOT/'tools/experiments/start_batch_remote.py'),'--worker'],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    print(json.dumps({'batch_pid':child.pid,'cases':len(batch_specs),'batch_spec':str(batch)}))
