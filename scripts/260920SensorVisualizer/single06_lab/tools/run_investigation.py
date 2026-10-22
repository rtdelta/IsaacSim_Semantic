"""Full staged investigation: AB/BA, controlled host pool, lifecycle and interaction."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from lab.runner import run,write
from lab.analysis import analyze
from lab.interaction import run_interaction

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--groups',type=int,default=4)
    p.add_argument('--repetitions',type=int,default=2);p.add_argument('--skip-interaction',action='store_true');a=p.parse_args()
    out=Path(a.output);out.mkdir(parents=True,exist_ok=False)
    matrix=json.loads((ROOT/'config/matrix.json').read_text());source=matrix['trajectory'];specs=[]
    for rep in range(a.repetitions):
        cases=matrix['cases'] if rep%2==0 else list(reversed(matrix['cases']))
        for c in cases:specs.append({**c,'name':str(rep)+'_'+c['name'],'repetition':rep,'groups':a.groups,'trajectory':source})
    specs.extend([
        {'name':'host_pool','host_pool':True,'groups':a.groups,'policy':'gated','pose':'moving','trajectory':source},
        {'name':'persistent_episodes','episodes':3,'groups':2,'policy':'gated','pose':'moving','trajectory':source},
        {'name':'trace_initialize','trace_window':'initialize','groups':1,'policy':'gated','pose':'moving','trajectory':source},
        {'name':'trace_cleanup','trace_window':'cleanup','groups':1,'policy':'gated','pose':'moving','trajectory':source},
    ])
    write(out/'plan.json',{'specs':specs,'quality_unchanged':True});results=[]
    for spec in specs:
        write(out/'progress.json',{'state':'running','active':spec['name'],'completed':len(results),'total':len(specs)+2})
        r=run(spec,out/spec['name']);results.append(r);write(out/'results.json',results)
        if r['exit_code']!=0 or not r.get('validation',{}).get('passed') or not r.get('profile_capture_verified',True) or r.get('external_stop_signal'):
            write(out/'progress.json',{'state':'failed','active':spec['name'],'completed':len(results)});return 1
        analyze(out/spec['name'])
    if not a.skip_interaction:
        for concurrent in (False,True):
            name='interaction_concurrent' if concurrent else 'interaction_only'
            write(out/'progress.json',{'state':'running','active':name,'completed':len(results)})
            r=run_interaction({'concurrent':concurrent,'seconds':30,'groups':a.groups,'policy':'gated','pose':'moving','trajectory':source},out/name)
            results.append(r);write(out/'results.json',results)
            if not r['passed']:return 1
    write(out/'progress.json',{'state':'finished','completed':len(results)});return 0
if __name__=='__main__':raise SystemExit(main())
