"""Sequential owned experiments; no sensor data processing on capture path."""
import argparse,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser();p.add_argument('suite',choices=['ordinary','diagnostic','final']);a=p.parse_args()
 out=Path('/root/gpufree-data/semantic/output/native_capture_baseline')/('wave_'+a.suite+'_'+time.strftime('%Y%m%d_%H%M%S',time.gmtime()))
 out.mkdir(exist_ok=False)
 if a.suite=='ordinary':
  cases=[('A_render',['--mode','render','--frames','60']),('B_publish',['--mode','publish','--frames','60']),
    ('C_record',['--mode','record','--frames','60']),('D_moving',['--mode','record','--motion','moving','--frames','60'])]
 elif a.suite=='diagnostic':
  cases=[('T_trace',['--mode','record','--trace','--frames','24']),
    ('F_frozen',['--mode','record','--schedule','frozen','--frames','2']),
    ('M_multitick',['--mode','record','--multi-tick','--frames','60'])]
 else:
  cases=[('E_final_record',['--mode','record','--frames','12','--warmup','8']),
    ('A_trace_render',['--mode','render','--trace','--frames','24'])]
 progress={'suite':a.suite,'directory':str(out),'cases':[],'state':'running'}
 def save():
  (out/'wave_progress.json').write_text(json.dumps(progress,indent=2))
  (ROOT/'reports/latest_execution.json').write_text(json.dumps({'pid':__import__('os').getpid(),'directory':str(out),'kind':'wave'},indent=2))
 for name,args in cases:
  progress['current']=name;save()
  with (out/(name+'.runner.log')).open('xb') as log:
   r=subprocess.run([sys.executable,'-u',str(ROOT/'run.py'),*args,'--output',str(out/name)],stdout=log,stderr=log)
  data=json.loads((out/name/'result.json').read_text()) if (out/name/'result.json').exists() else {'state':'failed'}
  progress['cases'].append({'name':name,'exit_code':r.returncode,'state':data['state'],'capture':data.get('capture'),
    'validation_ok':data.get('validation',{}).get('ok'),'errors':data.get('validation',{}).get('errors',[])})
  save()
  if r.returncode and a.suite=='ordinary':break
 progress['state']='completed' if len(progress['cases'])==len(cases) and all(c['exit_code']==0 for c in progress['cases']) else 'incomplete'
 progress.pop('current',None);save();print(json.dumps(progress))
if __name__=='__main__':main()
