"""Local/post-run analysis; preserves the strict MCAP failure independently."""
import hashlib,json,statistics,sys
from pathlib import Path
import numpy as np
from PIL import Image

def analyze(directory):
 out=Path(directory);spec=json.loads((out/'spec.json').read_text())
 groups=[json.loads(l) for l in (out/'groups.jsonl').read_text().splitlines()]
 sensors=json.loads((out/'sensor_manifest.json').read_text())['sensors'];checks=[]
 for g in groups:
  images=[]
  for s in sensors:
   if s['kind']!='camera':continue
   files=list((out/'native_basic_images'/('NativeBaseline_'+s['id'])/'rgb').glob(f"rgb_{g['group']:04d}.png"))
   matches=False
   if len(files)==1:
    rgb=np.ascontiguousarray(np.asarray(Image.open(files[0]).convert('RGB')))
    matches=hashlib.sha256(rgb.tobytes()).hexdigest()==g['images'][s['topic']]['sha256']
   images.append({'sensor':s['id'],'matches_final_observer':matches})
  settings=g['settings'];budget=(spec['pt_total_spp']%spec['pt_spp']==0 and
   g['sdk_subframes_at_capture']==spec['pt_total_spp']//spec['pt_spp'] and g['accumulation_reset'] and
   settings['/rtx/rendermode']=='PathTracing' and settings['/rtx/pathtracing/totalSpp']==spec['pt_total_spp'] and
   settings['/rtx/pathtracing/spp']==spec['pt_spp'] and settings['/rtx/pathtracing/adaptiveSampling/enabled'] is False)
  checks.append({'group':g['group'],'native_budget_complete':bool(budget),'image_checks':images,
   'begin_to_capture_s':g['native_frame_scheduled_s'],'begin_to_observed_payload_s':g['payload_observed_scope_s']})
 strict=json.loads((out/'group_validation.json').read_text());native=json.loads((out/'continuous_result.json').read_text())
 r={'requested_groups':spec['measure_frames'],'observed_groups':len(groups),'image_count':sum(len(x['image_checks']) for x in checks),
  'rendering_budget_and_final_image_checks_pass':len(groups)==spec['measure_frames'] and all(x['native_budget_complete'] and all(i['matches_final_observer'] for i in x['image_checks']) for x in checks),
  'mcap_strict_group_validation_pass':strict['ok'],'native_scenario_wall_s':native['native_scenario_wall_s'],
  'observed_group_seconds_mean':statistics.mean(g['payload_observed_scope_s'] for g in groups),'groups':checks,
  'limits':['This rendering-only success does not override failed strict MCAP/TF/joint timestamp validation.',
   'Verified renderer request and SDK completion do not prove hardware executed exactly 1024 rays per pixel.',
   'Frame-to-observer intervals overlap native next-frame work; they are not additive total duration.']}
 (out/'continuous_analysis.json').write_text(json.dumps(r,indent=2));return r
if __name__=='__main__':
 r=analyze(sys.argv[1]);print(json.dumps({k:v for k,v in r.items() if k!='groups'}))
