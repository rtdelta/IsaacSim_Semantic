"""Correlate control long tails with owned capture lifecycle on one host clock."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from lab.analysis import load_rows
p=argparse.ArgumentParser();p.add_argument('directory');a=p.parse_args();directory=Path(a.directory)
capture=directory/'capture';rows=load_rows(capture)
phases=[r for r in rows if r['event']=='span_end' and r.get('name') in (
 'lab.SceneStepper.initialize','lab.SceneStepper.advance_clock','lab.SensorDrivers.warm_cameras',
 'lab.SensorDrivers.acquire','lab.SceneStepper.close','lab.RecordPipeline.finish')]
resources=[json.loads(l) for l in (capture/'system_resources.jsonl').read_text().splitlines()]
origin=resources[0]['host_monotonic_ns'];finish=origin+int(json.loads((capture/'result.json').read_text())['process_wall_s']*1e9)
first=min(r['start_ns'] for r in phases);closed=max(r['start_ns']+r['duration_ns'] for r in phases)
commands=[json.loads(l) for l in (directory/'commands.jsonl').read_text().splitlines()];result=[]
for c in sorted(commands,key=lambda c:c['applied_ms'],reverse=True)[:20]:
 end=c.get('completed_ns',c['host_monotonic_ns']);start=c.get('accepted_ns',end-int(c['applied_ms']*1e6));mid=(start+end)//2
 matches=[r for r in phases if r['start_ns']<=mid<=r['start_ns']+r['duration_ns']]
 phase=matches[-1]['name'] if matches else 'Kit application startup before SceneStepper' if mid<first else 'Kit application shutdown after SceneStepper.close' if mid>=closed and mid<=finish+int(1e9) else 'Between observed stages / post-validation'
 result.append({'applied_ms':c['applied_ms'],'command_mid_after_sampler_s':(mid-origin)/1e9,
  'capture_phase':phase,'clock_evidence':'exact receipt timestamps' if 'completed_ns' in c else 'receipt-observed approximation; status polling adds delay'})
out={'longest_commands':result,'limits':['Temporal correlation does not identify a private driver lock or prove causality.',
 'Existing trials recorded exact latency but not receipt timestamps; phase labels use observed receipt time. New trials retain accepted_ns/completed_ns.']}
(directory/'interaction_attribution.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
