"""Produce an evidence inventory; never promote short screening to acceptance."""
import argparse,collections,json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from lab.analysis import stats
p=argparse.ArgumentParser();p.add_argument('directory');a=p.parse_args();out=Path(a.directory)
results=json.loads((out/'results.json').read_text());cases=collections.defaultdict(list)
summary={'directory':str(out),'limits':['4-group short screening; P95/P99 long-tail benefit unproven.',
 'Same hardware / scene / resolution / subframes; fixed-pose cases intentionally change trajectory pose only.',
 'Traced cases are not throughput measurements; SDK and driver internal attribution requires native stacks.'],
 'cases':{},'validation':[],'interaction':[],'warnings':{},'native_windows':{}}
for r in results:
 spec=r['spec'];name=spec.get('name','interaction')
 if 'exit_code' not in r:
  summary['interaction'].append(r);continue
 if r.get('profiled'):summary['native_windows'][name]=r.get('native_files');continue
 cases[name.split('_',1)[1] if name[:1].isdigit() else name].append(r)
 for v in r.get('episode_validations',[r.get('validation',{})]):
  summary['validation'].append({k:v.get(k) for k in ('passed','groups','lidars','cameras','tf_edges','tf_matrix_max_abs_error','writer_digests_match','root_unchanged')})
 case_directory=out/Path(r['directory']).name
 for w in case_directory.glob('captures/runs/*/diagnostics/warnings.json'):
  for row in json.loads(w.read_text()):
   key=row['code']+' '+row['sample'];summary['warnings'].setdefault(key,{'count':0,'cases':[]})
   summary['warnings'][key]['count']+=row['count'];summary['warnings'][key]['cases'].append(name)
for name,rr in cases.items():
 summary['cases'][name]={'runs':len(rr),'groups_per_s':stats([r.get('capture',{}).get('wall_groups_per_s') for r in rr]),
  'process_wall_s':stats([r.get('process_wall_s') for r in rr]),'groups':[r.get('validation',{}).get('groups') for r in rr],
  'directory':[r['directory'] for r in rr]}
base=summary['cases'].get('gated_moving',{}).get('groups_per_s',{}).get('mean')
for name in ('keepalive_moving','host_pool'):
 value=summary['cases'].get(name,{}).get('groups_per_s',{}).get('mean')
 if value and base:summary['cases'][name]['screening_throughput_ratio_vs_gated_moving']=value/base
for path in out.glob('interaction*/interaction_result.json'):
 r=json.loads(path.read_text())
 if not any(x.get('directory')==r.get('directory') for x in summary['interaction']):summary['interaction'].append(r)
(out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
