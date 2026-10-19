"""All-target pairing, decoded payload readback, independent geometry and metrics."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
from PIL import Image
PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT))
from tools.experiments.storage import rows,save,verify


def quantiles(values):
    values=sorted(float(x) for x in values if x is not None and math.isfinite(float(x)))
    return {str(p):values[max(0,math.ceil(p*len(values))-1)] if values else None for p in (.5,.95,.99,1.)}


def payload(directory,row):
    path=directory/row['payload_path']
    if row['kind']=='camera':
        with Image.open(path) as image:
            image.load()
            if image.mode!='RGB':raise ValueError('PNG mode differs from owned RGB')
            value=np.array(image)
    else:value=np.fromfile(path,dtype='<f4').reshape(row['shape'])
    if list(value.shape)!=row['shape'] or value.nbytes!=row['raw_nbytes'] or not np.isfinite(value).all():raise ValueError('Decoded payload layout differs')
    if hashlib.sha256(value.tobytes()).hexdigest()!=row['payload_sha256']:raise ValueError('Decoded payload SHA mismatch')
    return value


def geometry(xyz,matrix,walls):
    world=xyz.astype(float)@np.array(matrix)[:3,:3]+np.array(matrix)[3,:3]
    distances=np.column_stack([np.abs(world[:,wall['axis']]-wall['coordinate_m']) for wall in walls])
    residual=distances.min(axis=1);order=np.argsort(distances,axis=1)
    axes=np.array([w['axis'] for w in walls]);coordinates=np.array([w['coordinate_m'] for w in walls])
    keep=(distances[np.arange(len(xyz)),order[:,1]]-residual)>=.05
    keep &= axes[order[:,0]]<2
    chosen=order[keep,0];axis=axes[chosen];target=coordinates[chosen]
    vectors=world[keep]-np.array(matrix)[3,:3];origin=np.array(matrix)[3,:3];delta=0.
    fit=None
    if len(vectors):
        for _ in range(4):
            c,s=math.cos(delta),math.sin(delta)
            rotated=np.column_stack((c*vectors[:,0]-s*vectors[:,1],s*vectors[:,0]+c*vectors[:,1]))
            jac=np.column_stack((-rotated[:,1],rotated[:,0]))[np.arange(len(axis)),axis]
            err=rotated[np.arange(len(axis)),axis]+origin[axis]-target;den=float(jac@jac)
            if den<=1e-12:break
            delta-=float(jac@err)/den
        if abs(delta)<=math.radians(.2):fit=delta
    return {'point_plane_m':quantiles(residual),'yaw_fit_rad':fit,'yaw_fit_points':int(keep.sum()),
        'passes_5mm':quantiles(residual)['0.95']<=.005,'passes_observable_yaw':abs(fit)<=1e-4 if fit is not None else None}


def analyze(parent):
    parent=Path(parent);spec=json.loads((parent/'experiment_spec.json').read_text());cdir=parent/'continuous'
    fdir=parent/('frozen_v06' if spec['scene']=='scene18' else 'frozen_room');out=parent/'analysis';out.mkdir(exist_ok=True)
    file_counts={'C':verify(cdir),'F':verify(fdir)}
    ce=rows(cdir/'native_events.jsonl');fe=rows(fdir/'native_events.jsonl');targets=rows(cdir/'targets.jsonl')
    applied={r['target_index']:r for r in rows(fdir/'applied_states.jsonl')}
    results={r['target_index']:r for r in rows(fdir/'capture_results.jsonl')}
    states={r['physical_step']:r for r in rows(cdir/'actual_states.jsonl')}
    cs={};fs={}
    for row in ce:cs.setdefault((row['target_index'],row['sensor_id']),[]).append(row)
    for row in fe:fs.setdefault((row['target_index'],row['sensor_id']),[]).append(row)
    expected=json.loads((cdir/'run_result.json').read_text())['expected_sensors'];pair_map=[];metrics=[];geo=[]
    walls=json.loads((cdir/'render_profile.json').read_text()).get('room_geometry')
    # Verify all retained events, including rejected retries and repeated identities.
    for directory,events in ((cdir,ce),(fdir,fe)):
        for row in events:payload(directory,row)
    for index in range(spec['targets']):
        qualified=applied.get(index,{}).get('input_equivalence',{}).get('passed',False)
        qualified &= results.get(index,{}).get('input_equivalence_after',{}).get('passed',False)
        for sid in expected:
            c=cs.get((index,sid),[]);f=fs.get((index,sid),[])
            # Final accepted attempt is explicitly recorded; never select by geometric closeness.
            accepted=results.get(index,{}).get('accepted_attempt_id',results.get(index,{}).get('bundle',{}).get('attempt_id'))
            fa=[r for r in f if r.get('attempt_id',0)==accepted] if accepted is not None else f
            comparable=bool(qualified and len(c)==1 and len(fa)==1)
            mapping={'experiment_id':spec['experiment_id'],'repeat':spec['repeat'],'source_epoch':c[0]['source_epoch'] if c else None,
                'target_index':index,'source_target_step':targets[index]['physical_step'] if index<len(targets) else None,
                'sensor_id':sid,'C_events':len(c),'F_attempt_events':len(f),'F_accepted_events':len(fa),'input_qualified':bool(qualified),
                'comparable':comparable,'C_receipt_seq':c[0]['receipt_seq'] if len(c)==1 else None,
                'F_receipt_seq':fa[0]['receipt_seq'] if len(fa)==1 else None}
            pair_map.append(mapping)
            if not comparable:continue
            cr,fr=c[0],fa[0];cv=payload(cdir,cr);fv=payload(fdir,fr)
            item={'target_index':index,'source_target_step':cr['physical_step'],'sensor_id':sid,'kind':cr['kind'],
                'C_native_translation_m':cr['translation_error_m'],'F_native_translation_m':fr['translation_error_m'],
                'C_native_rotation_rad':cr['rotation_error_rad'],'F_native_rotation_rad':fr['rotation_error_rad'],
                'C_source_time_ns':cr['source_time_ns'],'F_source_time_ns':fr['source_time_ns'],
                'F_time_error_ns':int(fr['source_time_ns'])-int(fr['expected_time_ns']),
                'C_native_pose_pass':cr['translation_error_m']<=.001 and cr['rotation_error_rad']<=1e-4,
                'F_native_pose_pass':fr['translation_error_m']<=.001 and fr['rotation_error_rad']<=1e-4}
            if cr['kind']=='camera':
                difference=cv.astype(float)-fv.astype(float);mse=float(np.mean(difference*difference))
                item.update(image_mse=mse,image_psnr_db=10*math.log10(255**2/mse) if mse else None,image_identical=mse==0,
                    image_mae=float(np.mean(np.abs(difference))),image_quality_pass=None)
                # Fixed full-frame and centre/edge ROIs are descriptive, no post-hoc pass threshold.
                h,w=cv.shape[:2];item['fixed_roi_mae']={name:float(np.mean(np.abs(difference[ys,xs]))) for name,ys,xs in [
                    ('centre',slice(h//3,2*h//3),slice(w//3,2*w//3)),('left_edge',slice(None),slice(0,w//10)),
                    ('right_edge',slice(None),slice(9*w//10,w))]}
            else:
                item.update(C_points=len(cv),F_points=len(fv),row_identity_comparison=False)
                if walls and len(cv) and len(fv):
                    cg=geometry(cv,cr['historical_to_world'],walls);fg=geometry(fv,fr['historical_to_world'],walls)
                    previous=states.get(cr['physical_step']-1)
                    negative=geometry(cv,previous['sensor_world_matrices_usd'][sid],walls) if previous else None
                    geo.append({'target_index':index,'source_target_step':cr['physical_step'],'C':cg,'F':fg,'previous_actual_negative_control':negative})
                else:
                    try:
                        from scipy.spatial import cKDTree
                        a=cv.astype(float)@np.array(cr['historical_to_world'])[:3,:3]+np.array(cr['historical_to_world'])[3,:3]
                        b=fv.astype(float)@np.array(fr['historical_to_world'])[:3,:3]+np.array(fr['historical_to_world'])[3,:3]
                        item['world_surface_C_to_F_m']=quantiles(cKDTree(b).query(a[::max(1,len(a)//4096)])[0])
                        item['world_surface_F_to_C_m']=quantiles(cKDTree(a).query(b[::max(1,len(b)//4096)])[0])
                        item['surface_metric_scope']='unregistered spatial surface distance; no ray identity or absolute sync proof'
                    except ImportError:item['surface_metric_unavailable']='CPU scipy unavailable; no dependency downloaded'
            metrics.append(item)
    for name,data in [('pair_map.jsonl',pair_map),('analysis/paired_metrics.jsonl',metrics),('analysis/geometry_metrics.jsonl',geo)]:
        path=parent/name;path.write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in data))
    mcap=None
    if spec['scene']=='scene18':
        env=os.environ.copy()
        for key in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD','VIRTUAL_ENV','CONDA_PREFIX'):env.pop(key,None)
        run=subprocess.run(['/bin/bash','--noprofile','--norc','-c','source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 -B "$@"',
            'paired-readback',str(PROJECT.parent/'tools/validate_capture_data.py'),str(fdir)],env=env,capture_output=True,text=True,timeout=180)
        (out/'mcap_readback.log').write_text(run.stdout+'\n'+run.stderr)
        line=next((line for line in run.stdout.splitlines() if line.startswith('VALIDATION_JSON=')),None)
        mcap=json.loads(line.split('=',1)[1]) if line else {'passed':False,'returncode':run.returncode,'failure':run.stderr[-3000:]}
        save(out/'mcap_readback.json',mcap)
    c_bad=sum(not m['C_native_pose_pass'] for m in metrics);f_bad=sum(not m['F_native_pose_pass'] for m in metrics)
    summary={'schema_version':1,'experiment_completed':len(metrics)==spec['targets']*len(expected),
        'raw_capture_integrity_ok':True,'planned_target_coverage':len(metrics)/(spec['targets']*len(expected)),
        'pair_input_equivalence_ok':all(p['input_qualified'] for p in pair_map),
        'input_qualification_scope':'actual root, joints, mounts and sensor matrices; scene lighting audited separately',
        'camera_lighting_equivalent':bool(spec.get('align_v06_lighting')) if spec['scene']=='scene18' else None,
        'camera_lighting_note':'C preserves authored two DomeLights; original F selects one, so image differences are confounded' if spec['scene']=='scene18' and not spec.get('align_v06_lighting') else None,
        'native_source_mapping_ok':all(abs(m['F_time_error_ns'])<=2 for m in metrics),
        'native_pose_ok':{'C':c_bad==0 if metrics else None,'F':f_bad==0 if metrics else None},'native_pose_bad_events':{'C':c_bad,'F':f_bad},
        'independent_geometry_ok':{'C':all(g['C']['passes_5mm'] and g['C']['passes_observable_yaw'] for g in geo) if geo else None,
            'F':all(g['F']['passes_5mm'] and g['F']['passes_observable_yaw'] for g in geo) if geo else None},
        'image_quality_comparison':{'evaluated':sum(m['kind']=='camera' for m in metrics),'passed':None,
            'mae':quantiles([m.get('image_mae') for m in metrics]),'psnr_db':quantiles([m.get('image_psnr_db') for m in metrics])},
        'comparison_scope':spec,'counts':{'planned_sensor_targets':len(pair_map),'qualified_comparable':len(metrics),'C_events':len(ce),'F_attempt_events':len(fe),
            'C_duplicates':sum(max(0,len(v)-1) for v in cs.values()),'verified_files':file_counts},
        'native_rotation_rad':{'C':quantiles([m['C_native_rotation_rad'] for m in metrics]),'F':quantiles([m['F_native_rotation_rad'] for m in metrics])},
        'mcap_readback_ok':mcap['passed'] if mcap else None,
        'geometry':{'C_max_group_p95_m':max((g['C']['point_plane_m']['0.95'] for g in geo),default=None),
            'F_max_group_p95_m':max((g['F']['point_plane_m']['0.95'] for g in geo),default=None),
            'C_max_abs_yaw_fit_rad':max((abs(g['C']['yaw_fit_rad']) for g in geo if g['C']['yaw_fit_rad'] is not None),default=None),
            'F_max_abs_yaw_fit_rad':max((abs(g['F']['yaw_fit_rad']) for g in geo if g['F']['yaw_fit_rad'] is not None),default=None)},
        'mechanism_supported':['frozen/continuous difference under qualified actual states'] if c_bad and not f_bad else [],
        'mechanism_unresolved':['GPU detection pose versus output coordinate conversion','native history endpoint/interpolation branch','image reprojection in independent marked geometry'],
        'next_discriminating_experiment':'paired no-noise room, then original GMO independent decode and angle/direction/physics-step controls',
        'formal_continuous_acceptance':False}
    save(out/'summary.json',summary);print(json.dumps(summary))
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory');args=parser.parse_args();analyze(args.directory)
