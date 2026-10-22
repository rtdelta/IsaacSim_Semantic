"""Longer ordinary confirmation, graphical metrics, and repaired control trial.

No change to the frozen baseline or sensor quality. Failed candidates stay failed.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from lab.runner import run,write
from lab.interaction import run_interaction

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
 out=Path(a.output);out.mkdir(parents=True,exist_ok=False)
 source=json.loads((ROOT/'config/matrix.json').read_text())['trajectory']
 base={'pose':'moving','trajectory':source,'groups':16,'timeout_s':600}
 specs=[{**base,'name':'confirmation_gated','policy':'gated'},
  {**base,'name':'confirmation_keepalive','policy':'keepalive'},
  {**base,'name':'trace_graphics','groups':2,'policy':'keepalive','trace_window':'steady',
    'full_group_window':True,'metrics_set':'ad10x-gfxt','metrics_hz':10000}]
 write(out/'plan.json',{'specs':specs,'limit':'16 groups per policy supplements earlier AB/BA; not P99 acceptance'})
 results=[]
 for spec in specs:
  write(out/'progress.json',{'state':'running','active':spec['name'],'completed':len(results)})
  results.append(run(spec,out/spec['name']));write(out/'results.json',results)
 for concurrent in (False,True):
  name='interaction_gated' if concurrent else 'interaction_only'
  write(out/'progress.json',{'state':'running','active':name,'completed':len(results)})
  results.append(run_interaction({**base,'concurrent':concurrent,'seconds':30,'groups':4,'policy':'gated'},out/name))
  write(out/'results.json',results)
 write(out/'progress.json',{'state':'finished','completed':len(results)})
if __name__=='__main__':main()
