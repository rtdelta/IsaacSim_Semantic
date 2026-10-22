"""Cross-run attribution gates and fixed-denominator comparisons; no pose correction."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_instant_baseline.io import rows,save,sha
from tools.native_instant_baseline.math_independent import difference

def compare(a,b,frozen):
    def read(p,n):return json.loads((p/n).read_text())
    fa=read(a,'continuous/configuration_fingerprint.json');fb=read(b,'continuous/configuration_fingerprint.json')
    ap=read(a,'continuous/planned_targets.json');bp=read(b,'continuous/planned_targets.json')
    am=read(a,'analysis/target_metrics.json');bm=read(b,'analysis/target_metrics.json')
    checks={k:fa[k]==fb[k] for k in ('sensor_attributes_sha256','environment','effective','topology','scene')}
    checks['both_match_frozen_E']=all(f['sensor_attributes_sha256']==frozen['observed']['sensor_attributes_sha256'] and f['environment']==frozen['observed']['environment']
        and f['effective']==frozen['observed']['effective'] and f['scene']==frozen['observed']['scene'] for f in (fa,fb))
    # Product creation step is captured per run; probe E predates this diagnostic field.
    checks['topology_matches_E']=all({k:v for k,v in f['topology'].items() if k!='initialization'}=={k:v for k,v in frozen['observed']['topology'].items() if k!='initialization'} for f in (fa,fb))
    aa={r['physical_step']-ap['start_motion_step']:r['matrix'] for r in rows(a/'continuous/baseline_physics.jsonl') if r['phase']=='physics_post_actual' and ap['start_motion_step']<=r['physical_step']<=ap['end']}
    bb={r['physical_step']-bp['start_motion_step']:r['matrix'] for r in rows(b/'continuous/baseline_physics.jsonl') if r['phase']=='physics_post_actual' and bp['start_motion_step']<=r['physical_step']<=bp['end']}
    checks['same_local_motion_steps']=set(aa)==set(bb)
    errors=[difference(aa[k],bb[k]) for k in sorted(aa.keys()&bb.keys())]
    checks['all_step_actual_input_equivalent']=bool(errors) and all(p<=1e-5 and r<=1e-6 for p,r in errors)
    checks['first_target_six_moving_steps']=ap['first']-ap['start_motion_step']+1==bp['first']-bp['start_motion_step']+1==6
    checks['same_relative_tick_phase']=[s-ap['start_motion_step'] for s in ap['steps']]==[s-bp['start_motion_step'] for s in bp['steps']]
    sa=read(a,'analysis/summary.json');sb=read(b,'analysis/summary.json')
    checks['both_measurement_qualified']=sa['measurement_qualified'] is True and sb['measurement_qualified'] is True
    boundary=read(a,'continuous/source_manifest.json');checks['minimal_dependency_boundary']=boundary.get('minimal_dependency_boundary_passed') is True
    delta=[i for i,(x,y) in enumerate(zip(am,bm)) if any(x[k]!=y[k] for k in ('clock_ok','native_pose_ok','geometry_absolute_ok'))]
    candidates=[i for i,(x,y) in enumerate(zip(am,bm)) if x.get('candidate',{}).get('best_members')!=y.get('candidate',{}).get('best_members')]
    return {'M':str(a),'P':str(b),'checks':checks,'pair_equivalence_qualified':all(checks.values()),
      'local_steps_compared':len(errors),'max_input_translation_m':max((p for p,r in errors),default=None),'max_input_rotation_rad':max((r for p,r in errors),default=None),
      'actual_matrices_bitwise_equal':aa==bb,'target_class_different_indices':delta,'candidate_different_indices':candidates,
      'M_native_failed':sa['native_pose_failed'],'P_native_failed':sb['native_pose_failed'],'M_absolute_failed':sa['geometry_absolute_failed'],'P_absolute_failed':sb['geometry_absolute_failed'],
      'M_increment_failed':sa['geometry_increment_failed'],'P_increment_failed':sb['geometry_increment_failed'],
      'M_summary_sha256':sha(a/'analysis/summary.json'),'P_summary_sha256':sha(b/'analysis/summary.json')}

def run():
    cfg=ROOT/'config/native_instant_baseline';order=json.loads((cfg/'run_order.json').read_text());frozen=json.loads((cfg/'effective_E.json').read_text());root=ROOT/'reports/native_instant_baseline'/order['experiment_id']
    all_results={}
    for phase in ('qualification','main'):
        specs=[json.loads((ROOT/p).read_text()) for p in order[phase]];pairs=[]
        for s in specs:
            if s['group']!='M_E':continue
            mate=next(x for x in specs if x['group']=='P_E' and x['profile']==s['profile'] and x['repeat']==s['repeat'])
            a,b=ROOT/s['output_relative'],ROOT/mate['output_relative']
            if not (a/'analysis/summary.json').exists() or not (b/'analysis/summary.json').exists():continue
            item=compare(a,b,frozen);pairs.append(item)
            save(a/'pair_equivalence.json',item);save(b/'pair_equivalence.json',item)
        expected=len(specs)//2;result={'phase':phase,'expected_pairs':expected,'completed_pairs':len(pairs),'pairs':pairs,
            'all_measurement_and_pair_qualified':len(pairs)==expected and all(x['pair_equivalence_qualified'] for x in pairs)}
        save(root/(phase+'_comparison.json'),result);all_results[phase]=result
    frozen_d=json.loads((cfg/'effective_D.json').read_text()) if (cfg/'effective_D.json').exists() else None
    for phase,ep in [('D_qualification','qualification'),('D_main','main')]:
        ds=[json.loads((ROOT/p).read_text()) for p in order.get(phase,[])];es=[json.loads((ROOT/p).read_text()) for p in order[ep]];pairs=[]
        for s in ds:
            mate=next(x for x in es if x['group']=='M_E' and x['profile']==s['profile'] and x['repeat']==s['repeat'])
            a,b=ROOT/mate['output_relative'],ROOT/s['output_relative']
            if not (a/'analysis/summary.json').exists() or not (b/'analysis/summary.json').exists():continue
            item=compare(a,b,frozen);checks=item['checks'];fa=json.loads((a/'continuous/configuration_fingerprint.json').read_text());fb=json.loads((b/'continuous/configuration_fingerprint.json').read_text())
            ea=json.loads(json.dumps(fa['effective']));ea['settings']['/rtx/scenedb/maxHistoryTransformCount']=8
            checks['effective']=ea==fb['effective'];checks.pop('both_match_frozen_E')
            checks['E_matches_E_D_matches_D']=all(f[k]==expected['observed'][k] for f,expected in [(fa,frozen),(fb,frozen_d)] for k in ('sensor_attributes_sha256','environment','effective','scene'))
            checks['D_minimal_dependency_boundary']=json.loads((b/'continuous/source_manifest.json').read_text()).get('minimal_dependency_boundary_passed') is True
            item['pair_equivalence_qualified']=all(checks.values());item['intervention']='Only effective transform history count 64 -> 8; M script unchanged'
            pairs.append(item);save(b/'configuration_equivalence.json',item)
        result={'phase':phase,'expected_pairs':len(ds),'completed_pairs':len(pairs),'pairs':pairs,'all_measurement_and_pair_qualified':len(pairs)==len(ds) and all(x['pair_equivalence_qualified'] for x in pairs)}
        save(root/(phase+'_comparison.json'),result);all_results[phase]=result
    print(json.dumps(all_results))
if __name__=='__main__':run()
