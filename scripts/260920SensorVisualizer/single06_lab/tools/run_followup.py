"""Follow-up to measured allocation/compilation evidence, not a formal default change."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from lab.runner import run,write
from lab.analysis import analyze
from lab.interaction import run_interaction
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=False)
source=json.loads((ROOT/'config/matrix.json').read_text())['trajectory']
base={'policy':'gated','pose':'moving','trajectory':source,'groups':4};specs=[
 {**base,'name':'rgb_immediate_copy','rgb_immediate_copy':True},
 {**base,'name':'camera_warm_routing','isolated_camera_warmup':True},
 {**base,'name':'trace_gated_stacks','groups':2,'trace_window':'steady','full_group_window':True,'native_memory_stacks':True},
 {**base,'name':'trace_keepalive_stacks','groups':2,'policy':'keepalive','trace_window':'steady','full_group_window':True,'native_memory_stacks':True},
 {**base,'name':'controlled_stop','stop_after_groups':1},
]
write(out/'plan.json',{'specs':specs});results=[]
for spec in specs:
 write(out/'progress.json',{'state':'running','active':spec['name'],'completed':len(results),'total':len(specs)+1})
 r=run(spec,out/spec['name']);results.append(r);write(out/'results.json',results)
 # Failed correctness is evidence against an optional candidate, not permission
 # to suppress checks. Continue other independent experiments after own cleanup.
 if r['exit_code']==0 and r.get('validation',{}).get('passed'):analyze(out/spec['name'])
 else:write(out/spec['name']/'candidate_rejected.json',{'reason':r.get('capture',{}),'exit_code':r['exit_code']})
write(out/'progress.json',{'state':'running','active':'interaction_keepalive','completed':len(results)})
r=run_interaction({**base,'concurrent':True,'policy':'keepalive'},out/'interaction_keepalive')
results.append(r);write(out/'results.json',results);write(out/'progress.json',{'state':'finished','completed':len(results)})
