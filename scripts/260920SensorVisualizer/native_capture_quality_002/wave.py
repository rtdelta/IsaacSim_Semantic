"""Sequential controlled cases, preserving failures and individual MCAP evidence."""
import argparse,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser();p.add_argument('suite',choices=['rt','pt','trace','control']);a=p.parse_args()
 out=Path('/root/gpufree-data/semantic/output/native_capture_quality_002')/('wave_'+a.suite+'_'+time.strftime('%Y%m%d_%H%M%S',time.gmtime()));out.mkdir(exist_ok=False)
 spec=json.loads((ROOT/'config/baseline.json').read_text());spec['experiment']=a.suite;spec['trace']=a.suite=='trace';spec['timeout_s']=1800
 if a.suite=='pt':spec.update(render_mode='PathTracing',pt_total_spp=64)
 if a.suite=='control':spec['bypass_native_simulation_gate']=False
 config=out/'run_config.json';config.write_text(json.dumps(spec,indent=2))
 (ROOT/'reports/latest_execution.json').write_text(json.dumps({'pid':__import__('os').getpid(),'directory':str(out/'capture'),'suite':a.suite},indent=2))
 with (out/'runner.log').open('xb') as log:
  r=subprocess.run([sys.executable,'-u',str(ROOT/'run.py'),'--config',str(config),'--output',str(out/'capture')],stdout=log,stderr=log)
 if (out/'capture/groups.jsonl').exists():
  with (out/'analysis.log').open('w') as log:
   subprocess.run(['/bin/bash','-c','source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 "$@"','nc002-analyze',str(ROOT/'tools/analyze_quality.py'),str(out/'capture')],stdout=log,stderr=log)
  with (out/'resource_analysis.log').open('w') as log:
   subprocess.run(['/usr/bin/python3',str(ROOT/'tools/analyze_results.py'),str(out/'capture')],stdout=log,stderr=log)
 (out/'wave_result.json').write_text(json.dumps({'exit_code':r.returncode,'directory':str(out/'capture')},indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
