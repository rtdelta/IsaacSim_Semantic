"""Bound and sample only the independent diagnostic process that this file starts."""
from pathlib import Path
import hashlib
import json
import os
import signal
import subprocess
import time

ROOT=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02')
OUT=Path(__file__).resolve().parent

def manifest():
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in ROOT.rglob('*') if p.is_file() and p.suffix in ('.py','.json','.md','.yaml','.toml','.sh')
            and not any(x in p.relative_to(ROOT).parts for x in ('reports','__pycache__'))}

def process(pid):
    try:
        fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        return {'ticks':int(fields[11])+int(fields[12]),'start':fields[19], 'parent':int(fields[1])}
    except (OSError,ValueError,IndexError): return None

def current_phase():
    try: return json.loads((OUT/'phase.json').read_text())['phase']
    except (OSError,ValueError): return 'kit_startup'

def main():
    before=manifest(); (OUT/'source_before.json').write_text(json.dumps(before,indent=2))
    env=os.environ.copy(); env['DISPLAY']=':20'; env['PYTHONDONTWRITEBYTECODE']='1'
    args=['/usr/bin/python3',str(ROOT/'run_capture.py'),'--gui','--exec',str(OUT/'kit_profile.py')]
    log=(OUT/'kit.log').open('wb')
    child=subprocess.Popen(args,cwd=str(ROOT),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    identity=process(child.pid)
    (OUT/'process.json').write_text(json.dumps({'pid':child.pid,'identity':identity,'command':args,'display':':20'}))
    started=time.monotonic(); prev={}; ticks=os.sysconf('SC_CLK_TCK'); descendants={}
    result={'state':'running','pid':child.pid}
    with (OUT/'resources.jsonl').open('a',buffering=1) as stream:
        while child.poll() is None:
            now=time.monotonic(); row={'elapsed_s':now-started,'phase':current_phase(),'threads':[]}
            for task in Path(f'/proc/{child.pid}/task').glob('[0-9]*'):
                try:
                    fields=(task/'stat').read_text().rsplit(')',1)[1].split(); total=int(fields[11])+int(fields[12])
                    old=prev.get(task.name); prev[task.name]=(now,total)
                    if old:
                        core=(total-old[1])/ticks/(now-old[0])
                        row['threads'].append({'tid':int(task.name),'name':(task/'comm').read_text().strip(),
                            'cpu_cores':round(core,4),'wait':(task/'wchan').read_text().strip()})
                except (OSError,ValueError,IndexError): pass
            row['cpu_cores']=round(sum(t['cpu_cores'] for t in row['threads']),4)
            row['threads']=sorted(row['threads'],key=lambda t:t['cpu_cores'],reverse=True)[:10]
            try:
                query=subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu,utilization.memory,memory.used,power.draw',
                                      '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=3)
                row['gpu']=query.stdout.strip()
            except Exception as exc: row['gpu_error']=str(exc)
            for path in Path('/proc').glob('[0-9]*'):
                info=process(path.name)
                if info and (info['parent']==child.pid or info['parent'] in descendants): descendants[int(path.name)]=info['start']
            stream.write(json.dumps(row)+'\n')
            if now-started>600:
                result['timeout']=True
                os.killpg(child.pid,signal.SIGTERM)
                try: child.wait(timeout=15)
                except subprocess.TimeoutExpired: os.killpg(child.pid,signal.SIGKILL); child.wait(timeout=10)
                break
            time.sleep(1)
    result.update(state='finished',exit_code=child.returncode,wall_s=time.monotonic()-started)
    # Any leftover child is task-owned and identified by its unchanged start tick.
    leftover=[]
    for pid,start in descendants.items():
        info=process(pid)
        if info and info['start']==start:
            try: os.kill(pid,signal.SIGTERM); leftover.append(pid)
            except ProcessLookupError: pass
    result['leftover_children_terminated']=leftover
    after=manifest(); (OUT/'source_after.json').write_text(json.dumps(after,indent=2))
    result['changed_source_paths']=[p for p in set(before)|set(after) if before.get(p)!=after.get(p)]
    result['source_file_count']=len(before)
    (OUT/'supervisor_result.json').write_text(json.dumps(result,indent=2)+'\n')
    log.close()

if __name__=='__main__': main()
