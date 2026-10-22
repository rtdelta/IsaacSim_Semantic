"""Finite preregistered stages, serial Kit only, terminal failures stop progression."""
import json,os,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_rotation_localization.io import save
SUITE=ROOT/'reports/native_rotation_localization/native007_20261015_v1'
DEST=SUITE/'declared_followup'
def terminal(sequence,limit):
 deadline=time.monotonic()+limit
 while time.monotonic()<deadline:
  path=SUITE/'sequences'/sequence/'status.json'
  if path.is_file():
   d=json.loads(path.read_text())
   if d['state'] in ('COMPLETE','TERMINAL_WITH_BLOCKED_BRANCHES'):return
   if d['state']!='running':raise RuntimeError(sequence+' '+d['state']+' '+str(d.get('failure')))
  time.sleep(5)
 raise RuntimeError('Stage deadline '+sequence)
def worker():
 state={'state':'running','stages':[]};env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
 try:
  for stage,sequence,starter in [('main','main_m02',None),('B3','extension_B3_q01','start_B3_remote.py'),('speed','extension_speed_m01','start_speed_remote.py'),('T3','extension_T3_q01','start_T3_remote.py')]:
   state['active']=stage;save(DEST/'status.json',state)
   if starter:subprocess.run(['/usr/bin/python3','-B',str(ROOT/'tools/native_rotation_localization'/starter)],check=True,env=env,timeout=60)
   terminal(sequence,7200)
   with (DEST/(stage+'_analysis.log')).open('xb') as log:
    subprocess.run(['/usr/bin/python3','-B',str(ROOT/'tools/native_rotation_localization/analyze_stage.py'),stage],check=True,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=900)
   d=json.loads((SUITE/'stage_analysis'/stage/'summary.json').read_text());state['stages'].append({'stage':stage,'all_pair_qualified':d['all_pair_qualified']})
   if not d['all_pair_qualified']:raise RuntimeError('Inspect pair/scan semantics before next stage '+stage)
  state['state']='COMPLETE'
 except Exception as exc:state.update(state='STOPPED_FOR_INSPECTION',failure=str(exc),traceback=traceback.format_exc())
 save(DEST/'status.json',state)
def start():
 DEST.mkdir(parents=True,exist_ok=False)
 with (DEST/'pipeline.log').open('xb') as log:
  child=subprocess.Popen(['/usr/bin/python3','-B',str(Path(__file__)),'--pipeline'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 print(json.dumps({'pid':child.pid,'scope':'Finite main analysis -> B3 qualification -> speed 100x3 -> independent C1/C2 qualification; stop on any failed prerequisite'}))
if __name__=='__main__':worker() if '--pipeline' in sys.argv else start()
