"""Bound only the independent process tree started by this test."""
from pathlib import Path
import hashlib,json,os,signal,subprocess,time
ROOT=Path(__file__).resolve().parents[1];OUT=Path(os.environ['SV04_TEST_OUT'])

def identity(pid):
    try:
        row=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        return {'start':row[19],'parent':int(row[1]),'state':row[0]}
    except (OSError,ValueError,IndexError):return None
def hashes(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*')
            if p.is_file() and p.suffix in ('.py','.json','.md','.sh','.toml')
            and not any(x in ('__pycache__','reports','deploy_history','generated') for x in p.relative_to(root).parts)}

def main():
    old=ROOT.parent/'v02';before=hashes(old)
    (OUT/'old_source_before.json').write_text(json.dumps(before,indent=2))
    env=os.environ.copy();env.update(DISPLAY=':20',PYTHONDONTWRITEBYTECODE='1')
    cmd=['/usr/bin/python3',str(ROOT/'run_capture.py'),'--gui','--exec',str(ROOT/'tools/kit_acceptance.py')]
    if os.environ.get('SV04_TEST_HEADLESS')=='1':
        job=json.loads((ROOT/'config/smoke.json').read_text())
        job['output_directory']=str(OUT/'captures')
        job['motion']={'tilt':{'roll':{'mode':'target','target':2,'speed':2}},
                       'base':{'speed_m_s':.05,'yaw_rate_deg_s':1}}
        job['diagnostics']={'level':'diagnostic','export_trace_on_stop':True}
        (OUT/'job.json').write_text(json.dumps(job,indent=2))
        cmd=['/usr/bin/python3',str(ROOT/'run_capture.py'),'--job',str(OUT/'job.json')]
    log=(OUT/'kit.log').open('wb')
    child=subprocess.Popen(cmd,cwd=str(ROOT),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    owned=identity(child.pid);start=time.monotonic();descendants={};result={}
    (OUT/'process.json').write_text(json.dumps({'pid':child.pid,'identity':owned,'command':cmd,'display':':20'}))
    while child.poll() is None:
        for p in Path('/proc').glob('[0-9]*'):
            row=identity(p.name)
            if row and (row['parent']==child.pid or row['parent'] in descendants):descendants[int(p.name)]=row['start']
        if time.monotonic()-start>900:
            result['timeout']=True;os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(timeout=15)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=10)
            break
        time.sleep(1)
    result.update(exit_code=child.returncode,wall_s=time.monotonic()-start)
    leftovers=[]
    for pid,tick in descendants.items():
        row=identity(pid)
        if row and row['start']==tick and row['state']!='Z':
            os.kill(pid,signal.SIGTERM);leftovers.append(pid)
    result['leftover_owned_children_terminated']=leftovers
    after=hashes(old)
    result['old_source_files']=len(before)
    result['changed_old_source']=[p for p in set(before)|set(after) if before.get(p)!=after.get(p)]
    (OUT/'supervisor_result.json').write_text(json.dumps(result,indent=2));log.close()

if __name__=='__main__':main()
