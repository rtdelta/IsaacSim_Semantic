"""Finite preregistered T3 confirmation and C0 coded-motion follow-up."""
import hashlib,json,os,subprocess,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_rotation_localization.io import save
from tools.native_rotation_localization.continue_declared import terminal
SUITE=ROOT/'reports/native_rotation_localization/native007_20261015_v1';DEST=SUITE/'stage2_followup'
def worker():
 state={'state':'running','stages':[]};env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
 try:
  for stage,name in [('confirm','extension_confirm_m01'),('coded','extension_coded_m01')]:
   state['active']=stage;save(DEST/'status.json',state)
   manifest=ROOT/'config/native_rotation_localization/v1'/(name+'_sequence.json');config=json.loads(manifest.read_text())
   for row in config['runs']:
    spec=json.loads((ROOT/row['spec']).read_text())
    if spec.get('motion')=='coded' and hashlib.sha256((ROOT/spec['frozen_input_path']).read_bytes()).hexdigest()!=spec['frozen_input_sha256']:raise RuntimeError('Frozen coded table SHA')
   subprocess.run(['/usr/bin/python3','-B',str(ROOT/'tools/native_rotation_localization/coordinator.py'),'--sequence',str(manifest)],check=True,env=env,timeout=60)
   terminal(name,7200)
   with (DEST/(stage+'_analysis.log')).open('xb') as log:
    subprocess.run(['/usr/bin/python3','-B',str(ROOT/'tools/native_rotation_localization/analyze_stage.py'),stage],check=True,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=900)
   d=json.loads((SUITE/'stage_analysis'/stage/'summary.json').read_text());state['stages'].append({'stage':stage,'all_pair_qualified':d['all_pair_qualified']})
   if not d['all_pair_qualified']:
    if stage!='confirm':raise RuntimeError('Stage comparison prerequisite failed '+stage)
    from tools.native_rotation_localization.intervention_boundary import review
    boundary=review(stage)
    if not boundary['eligible_for_full_output_repeat']:raise RuntimeError('Changed prerequisites exceed preregistered return-set boundary')
    state['stages'][-1]['strict_pair_boundary_preserved']=True
  state['state']='COMPLETE'
 except Exception as exc:state.update(state='STOPPED_FOR_INSPECTION',failure=str(exc),traceback=traceback.format_exc())
 save(DEST/'status.json',state)
def start():
 prior=json.loads((SUITE/'declared_followup/status.json').read_text())
 if prior['state']!='COMPLETE':
  resume=SUITE/'sequences/extension_T3_resume_q01/status.json'
  if prior.get('active')!='T3' or not resume.is_file() or json.loads(resume.read_text())['state']!='TERMINAL_WITH_BLOCKED_BRANCHES':raise RuntimeError('Declared T3 or explicit independent-branch resumption not terminal')
 if not json.loads((SUITE/'stage_analysis/T3/intervention_confirmation_release.json').read_text())['eligible_for_full_output_repeat']:raise RuntimeError('T3 full-output repetition boundary failed')
 DEST.mkdir(parents=True,exist_ok=False)
 with (DEST/'pipeline.log').open('xb') as log:
  child=subprocess.Popen(['/usr/bin/python3','-B',str(Path(__file__)),'--pipeline'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 print(json.dumps({'pid':child.pid,'scope':'Finite qualified T3 confirmation then three independent coded C0 runs'}))
if __name__=='__main__':worker() if '--pipeline' in sys.argv else start()
