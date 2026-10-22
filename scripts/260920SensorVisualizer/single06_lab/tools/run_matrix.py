"""Interleaved AB/BA mechanism trials; traced runs kept out of throughput results."""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from lab.runner import run,write

def main():
    p=argparse.ArgumentParser();p.add_argument('--matrix',default=str(ROOT/'config/matrix.json'))
    p.add_argument('--output',required=True);p.add_argument('--groups',type=int);p.add_argument('--repetitions',type=int)
    p.add_argument('--traces',action='store_true');a=p.parse_args()
    matrix=json.loads(Path(a.matrix).read_text());out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=False)
    specs=[]
    for rep in range(a.repetitions or matrix['repetitions']):
        cases=matrix['cases'] if rep%2==0 else list(reversed(matrix['cases']))
        for case in cases:
            specs.append({**case,'name':str(rep)+'_'+case['name'],'groups':a.groups or matrix['groups'],
                          'trajectory':matrix['trajectory'],'repetition':rep})
    if a.traces:
        for window in matrix['trace_windows']:
            specs.append({'name':'trace_'+window,'groups':3,'trajectory':matrix['trajectory'],
                          'policy':'gated','pose':'moving','trace_window':window,'trace_group':1})
    write(out/'plan.json',{'matrix':matrix,'execution_order':specs})
    results=[]
    for spec in specs:
        write(out/'progress.json',{'active':spec['name'],'completed':len(results),'total':len(specs)})
        result=run(spec,out/spec['name']);results.append(result);write(out/'matrix_results.json',results)
        if result['exit_code']!=0 or not result.get('validation',{}).get('passed'):
            write(out/'progress.json',{'state':'failed','active':spec['name'],'completed':len(results)});return 1
    write(out/'progress.json',{'state':'finished','completed':len(results),'total':len(specs)})
    return 0
if __name__=='__main__':raise SystemExit(main())
