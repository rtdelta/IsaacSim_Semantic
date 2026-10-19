"""Finite sequential execution of the frozen plan; each batch retains its own gates."""
import argparse,json,os,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_instant_baseline.io import save
from tools.native_instant_baseline.coordinator import start,processes

def work():
    cfg=ROOT/'config/native_instant_baseline';order=json.loads((cfg/'run_order.json').read_text());base=ROOT/'reports/native_instant_baseline'/order['experiment_id']
    status={'state':'running','pid':os.getpid(),'batches':order['batches'],'completed':[]};target=base/'sequence_status.json'
    try:
        for bid in order['batches']:
            bpath=cfg/(bid+'.json');b=json.loads(bpath.read_text());sp=ROOT/'reports/native_instant_baseline/batches'/bid/'status.json'
            if sp.exists():
                previous=json.loads(sp.read_text())
                if previous['state']!='COMPLETE':raise RuntimeError('Existing batch not complete: '+bid)
            else:
                if b['phase']=='D_main':subprocess.run([sys.executable,'-B',str(ROOT/'tools/native_instant_baseline/compare_runs.py')],check=True)
                if b['phase']=='main' and not (cfg/'main_code_lock.json').exists():
                    subprocess.run([sys.executable,'-B',str(ROOT/'tools/native_instant_baseline/compare_runs.py')],check=True)
                    subprocess.run([sys.executable,'-B',str(ROOT/'tools/native_instant_baseline/freeze_main_remote.py')],check=True)
                status['active_batch']=bid;save(target,status);start(bpath)
                deadline=time.monotonic()+len(b['specs'])*920+60
                while time.monotonic()<deadline:
                    time.sleep(2)
                    if not sp.exists():continue
                    current=json.loads(sp.read_text())
                    if current['state']=='COMPLETE':break
                    if current['state']!='running':raise RuntimeError('Batch stopped: '+bid+' '+current.get('failure',''))
                else:raise RuntimeError('Batch observation deadline: '+bid)
            status['completed'].append(bid);save(target,status)
        subprocess.run([sys.executable,'-B',str(ROOT/'tools/native_instant_baseline/compare_runs.py')],check=True)
        status['state']='COMPLETE'
    except Exception as exc:status.update(state='FAILED',failure=str(exc),traceback=traceback.format_exc())
    save(target,status)

def launch():
    if processes():raise RuntimeError('Existing Kit/coordinator')
    cfg=ROOT/'config/native_instant_baseline';order=json.loads((cfg/'run_order.json').read_text());base=ROOT/'reports/native_instant_baseline'/order['experiment_id'];base.mkdir(parents=True,exist_ok=True)
    if (base/'sequence_status.json').exists():raise RuntimeError('Sequence already launched; inspect its preserved state')
    env=os.environ.copy()
    for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):env[k]='1'
    for k in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(k,None)
    with (base/'sequence.log').open('xb') as log:
        p=subprocess.Popen([sys.executable,'-B',str(Path(__file__)),'--sequence'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    print(json.dumps({'sequence_pid':p.pid,'declared_batches':order['batches']}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sequence',action='store_true');a=p.parse_args();work() if a.sequence else launch()
