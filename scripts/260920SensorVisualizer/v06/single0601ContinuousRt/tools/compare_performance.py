"""Gate M5 claims on six actual alternating rounds and independent quality evidence."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def compare(spec,base):
    errors=[]
    rounds=spec.get('rounds',[])
    roles=[r.get('role') for r in rounds]
    if roles not in (['baseline','candidate']*3,['candidate','baseline']*3):
        errors.append('Exactly three alternating baseline and candidate rounds are required')
    baseline,candidate=[],[]
    reference=None
    evidence=[]
    for number,round in enumerate(rounds):
        directory=(base/round['directory']).resolve()
        perf=read(directory/'performance.json')
        validation=read(directory/'validation.json')
        job=read(directory/'job_spec.json')
        asset=read(directory/'asset_manifest.json')
        registry=read(directory/'sensor_registry.json')
        env=read(directory/'environment.json')
        profile=read(directory/'render_profile.json')
        signature={'assets':[(a['uri'],a['sha256']) for a in asset['dependencies'] if a['kind']!='anonymous runtime layer'],
            'sensor_ids':sorted(e['sensor_id'] for k in ('cameras','lidars') for e in registry[k]),
            'cameras':[(c['id'],[c['calibration']['width'],c['calibration']['height']],c['calibration']) for c in registry['cameras']],
            'clock':job['clock'],'encoding':{k:job['pipeline'][k] for k in ('png_compress_level','encoder_workers')},
            'trajectory_sha256':round.get('trajectory_sha256'),'workload':round.get('workload'),
            'effective_render':profile['effective'],'gpu':env['gpu'],'versions':env['versions']}
        # Scheduling and subframes are the tested variables, not quality settings.
        for k in ('formal_subframes',):
            signature['effective_render'].pop(k,None)
        if reference is None:reference=signature
        elif signature!=reference:errors.append('Round %s assets, sensors, trajectory, GUI workload or render settings differ'%number)
        if not round.get('trajectory_sha256') or round.get('workload')!='single_GUI_same_preview' or round.get('profiler') is not False:
            errors.append('Round %s has no verified trajectory/workload/no-profiler declaration'%number)
        if perf['warmup_excluded_groups']<20 or perf['measured_groups']<200:
            errors.append('Round %s did not exclude 20 warmup groups and measure at least 200'%number)
        if not all(validation.get(k) is True for k in ('sync_ok','completeness_ok','file_integrity_ok')):
            errors.append('Round %s has no independent complete readback'%number)
        if len(registry['cameras'])!=4 or len(registry['lidars'])!=13:
            errors.append('Round %s is not the required full scene18 selection'%number)
        if round['role']=='baseline' and (round.get('protocol')!='v06_unmodified_persistent_gated_keepalive_16_plus_2' or round.get('unmodified_source_verified') is not True):
            errors.append('Baseline protocol or unmodified source verification is missing')
        value=perf['throughput'].get('steady_usable_groups_per_wall_s')
        if not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
            errors.append('Round %s has no positive measured steady usable throughput'%number)
        else:
            (baseline if round['role']=='baseline' else candidate).append(value)
        evidence.append({'directory':str(directory),'role':round['role'],'throughput':value,
            'performance_sha256':hashlib.sha256((directory/'performance.json').read_bytes()).hexdigest(),
            'validation_sha256':hashlib.sha256((directory/'validation.json').read_bytes()).hexdigest()})
    quality=read(base/spec['quality_report']) if spec.get('quality_report') else {}
    if quality.get('quality_ok') is not True or not quality.get('evidence_paths') or not all(quality.get(k) is True for k in ('moving_details','fisheye_edges','occlusion_reveal','fast_rotation','resume_first_frame','geometry_ok')):
        errors.append('Independent motion/image/geometry quality acceptance is missing')
    speedup=statistics.median(candidate)/statistics.median(baseline) if len(candidate)==len(baseline)==3 else None
    qualified=not errors
    return {'schema_version':1,'scope':'M5 full-selection three alternating GUI rounds','rounds':evidence,
        'qualified_comparison':qualified,'median_baseline_groups_per_wall_s':statistics.median(baseline) if baseline else None,
        'median_candidate_groups_per_wall_s':statistics.median(candidate) if candidate else None,
        'speedup_vs_baseline':speedup if qualified else None,'performance_ok':speedup>=2 if qualified else None,
        'quality_ok':quality.get('quality_ok'),'errors':errors}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('spec',type=Path,help='JSON rounds [{role,directory,...}], quality_report')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        report=compare(read(a.spec),a.spec.resolve().parent)
    except Exception as exc:
        report={'schema_version':1,'qualified_comparison':False,'performance_ok':None,'speedup_vs_baseline':None,
                'errors':[type(exc).__name__+': '+str(exc)]}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    sys.exit(0 if report['performance_ok'] is True else 2)
