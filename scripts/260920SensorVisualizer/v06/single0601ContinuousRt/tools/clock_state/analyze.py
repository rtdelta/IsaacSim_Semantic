"""Read all saved events, preserve planned denominators, qualify analytic rays."""
import collections,hashlib,json,sys
from pathlib import Path
import numpy as np
PROJECT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(PROJECT),str(PROJECT.parent)]
from tools.experiments.storage import rows,save,verify,digest
from tools.experiments.compare_paired_outputs import payload,geometry,quantiles
from tools.experiments.decode_gmo import decode
from tools.experiments.analyze_mechanism_relations import ray_ranges
from tools.clock_state.candidates import RULES,candidates,classify
from tools.clock_state.common import tri


def quantiles(values):
    """Same declared nearest-rank statistic, without Python sorting every ray."""
    a=np.asarray(values,dtype=float).reshape(-1);a=a[np.isfinite(a)];levels=(.5,.95,.99,1.)
    if not len(a):return {str(p):None for p in levels}
    indices=[max(0,int(np.ceil(p*len(a)))-1) for p in levels];ordered=np.partition(a,indices)
    return {str(p):float(ordered[k]) for p,k in zip(levels,indices)}


def packet_bytes(directory,meta):
    path=directory/meta['packet_path']
    if path.suffix=='.gz':
        import gzip
        with gzip.open(path,'rb') as stream:
            data=stream.read(64*1024**2+1)
        if len(data)>64*1024**2:raise ValueError('Decompressed GMO exceeds declared maximum')
    else:data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=meta['packet_sha256']:raise ValueError('Original GMO SHA mismatch after lossless readback')
    return data


def analyze(parent,out_name='analysis'):
    if Path(out_name).name!=out_name or not out_name.startswith('analysis'):raise ValueError('Unsafe analysis output name')
    parent=Path(parent);spec=json.loads((parent/'experiment_spec.json').read_text());out=parent/out_name;out.mkdir(exist_ok=True)
    frozen_rules=json.loads((parent/'analysis_rules.json').read_text())
    if frozen_rules!=RULES:raise ValueError('Frozen analysis rules differ; require new version')
    cdir=parent/'continuous';fdir=parent/'frozen_room';verified={'continuous':verify(cdir),'frozen_room':verify(fdir)}
    registry=json.loads((cdir/'sensor_registry.json').read_text());params=registry['lidars'][0]['parameters']
    walls=json.loads((cdir/'render_profile.json').read_text())['room_geometry']
    def setting(name):
        v=params['omni:sensor:Core:emitterState:s001:'+name];return v['value'] if isinstance(v,dict) and 'value' in v else v
    for name in ('horOffsetM','vertOffsetM','distanceCorrectionM','fireTimeNs'):
        if np.any(np.asarray(setting(name))!=0):raise ValueError('Nonzero emitter '+name)
    az=np.deg2rad(setting('azimuthDeg'));el=np.deg2rad(setting('elevationDeg'))
    directions=np.column_stack((np.cos(el)*np.cos(az),-np.cos(el)*np.sin(az),np.sin(el)))
    raw=rows(cdir/'raw_receipts.jsonl');ce=rows(cdir/'native_events.jsonl');fe=rows(fdir/'native_events.jsonl')
    # Include warmup, drain, duplicate and unassigned payloads in independent SHA/layout readback.
    for directory,events in ((cdir,raw),(fdir,fe)):
        for row in events:
            if row.get('payload_path'):payload(directory,row)
            meta=row.get('native_event')
            if meta and meta.get('packet_path'):packet_bytes(directory,meta)
    targets={r['target_index']:r for r in rows(cdir/'targets.jsonl')};states={r['physical_step']:r for r in rows(cdir/'actual_states.jsonl')}
    applied={r['target_index']:r for r in rows(fdir/'applied_states.jsonl')};completed={r['target_index']:r for r in rows(fdir/'capture_results.jsonl')}
    byc=collections.defaultdict(list);byf=collections.defaultdict(list)
    for r in ce:byc[r['target_index']].append(r)
    for r in fe:
        if r.get('attempt_id')==completed.get(r['target_index'],{}).get('accepted_attempt_id'):byf[r['target_index']].append(r)
    component=[];metrics=[];cross=collections.Counter();decoded_equal=[];f_ray=[];gmo_headers=[];decode_failures=[]
    def ray_data(directory,row):
        meta=row.get('native_event')
        if not row.get('payload_path') or not meta or not meta.get('packet_path'):return None
        packet=packet_bytes(directory,meta)
        try:header,arrays,aux,xyz=decode(packet)
        except Exception as exc:
            decode_failures.append({'side':directory.name,'target_index':row['target_index'],'error':str(exc)});return None
        valid=(arrays['flags']&64)!=0
        if header['coordinates_type_code']!=0 or header['frame_of_reference_code']!=0 or not np.array_equal(np.asarray(header['model_to_app_transform_raw']).reshape(4,4),np.eye(4)):
            decode_failures.append({'side':directory.name,'target_index':row['target_index'],'error':'unqualified GMO coordinate model'});return None
        decoded=xyz[valid];extracted=payload(directory,row);equal=decoded.shape==extracted.shape and np.array_equal(decoded.astype('<f4'),extracted)
        decoded_equal.append(equal)
        gmo_headers.append({'side':directory.name,'target_index':row['target_index'],'header':header,'decoded_equals_extractor':equal,
            'point_time_offset_ns':quantiles(arrays['time_offset_ns'][valid])})
        if not equal:
            decode_failures.append({'side':directory.name,'target_index':row['target_index'],'error':'GMO/Extractor mismatch invalidates ray association'});return None
        if not len(extracted):return None
        nominal=directions[arrays['emitter_id'][valid]];ranges=np.linalg.norm(decoded.astype(float),axis=1)
        return nominal,ranges,extracted
    # F's qualification is evaluated before C candidate interpretation.
    fdata={}
    for index,events in byf.items():
        if len(events)!=1:continue
        row=events[0];data=ray_data(fdir,row)
        if data:
            nominal,ranges,xyz=data;err=quantiles(np.abs(ray_ranges(nominal,row['historical_to_world'],walls)-ranges))['0.95']
            f_ray.append(err);fdata[index]={'ray_p95_m':err,'geometry':geometry(xyz,row['historical_to_world'],walls),
                'clock_mapping_ok':abs(int(row['source_time_ns'])-int(row['expected_time_ns']))<=2,
                'native_pose_ok':row['translation_error_m']<=.001 and row['rotation_error_rad']<=1e-4,
                'native_clock_frozen':completed[index]['native_clock_frozen']}
    ray_qualified=len(f_ray)==spec['targets'] and all(x<=RULES['frozen_ray_p95_max_m'] for x in f_ray)
    for index in range(spec['targets']):
        c=byc[index];f=byf[index];target=targets.get(index)
        input_ok=bool(target and target['table_input_equivalence']['passed'] and applied.get(index,{}).get('input_equivalence',{}).get('passed') and completed.get(index,{}).get('input_equivalence_after',{}).get('passed'))
        item={'target_index':index,'C_events':len(c),'F_events':len(f),'input_qualified':input_ok,
            'clock_mapping_ok':None,'native_pose_ok':None,'geometry_ok':None,'event_provenance_ok':None,'payload_freshness_ok':None,
            'freshness_evidence_kind':'unavailable; current headers alone do not prove recomputation','C_geometry':None,'F':fdata.get(index)}
        if len(c)==1:
            row=c[0];item['clock_mapping_ok']=row['clock_mapping_ok']
            item['event_provenance_ok']=not row['formal_event_rejected']
            item['native_pose_ok']=(row['translation_error_m']<=.001 and row['rotation_error_rad']<=1e-4) if 'rotation_error_rad' in row else None
            item['native_rotation_rad']=row.get('rotation_error_rad');item['reference_delta_ns']=row.get('reference_delta_ns')
            data=ray_data(cdir,row)
            if data:
                nominal,ranges,xyz=data;geo=geometry(xyz,row['historical_to_world'],walls);item['C_geometry']=geo
                item['geometry_ok']=bool(geo['passes_5mm'] and geo['passes_observable_yaw']) if geo['passes_observable_yaw'] is not None else None
                old=[states.get(row['physical_step']-lag,{}).get('sensor_world_matrices_usd',{}).get(row['sensor_id']) for lag in (1,2)]
                poses=candidates(row['historical_to_world'],*old)
                residuals={name:quantiles(np.abs(ray_ranges(nominal,v['matrix'],walls)-ranges))['0.95'] for name,v in poses.items()}
                verdict=classify(poses,residuals);verdict.update(target_index=index,physical_step=row['physical_step'],
                    ray_model_qualified=ray_qualified,input_qualified=input_ok,interpretation_qualified=ray_qualified and input_ok,
                    candidates={name:dict(v,matrix=v['matrix'].tolist(),p95_m=residuals[name]) for name,v in poses.items()})
                component.append(verdict)
        key=','.join(tri(item[k]) for k in ('clock_mapping_ok','native_pose_ok','geometry_ok'));cross[key]+=1;item['joint_cell']=key;metrics.append(item)
    updates=rows(cdir/'app_updates.jsonl');motion=[u for u in updates if u['phase']=='motion_and_drain']
    deltas=[u['physical_step_after']-u['physical_step_before'] for u in motion]
    writes=rows(cdir/'pose_writes.jsonl');dts=[w['dt'] for w in writes]
    times=[int(s['sim_time_ns']) for s in sorted(states.values(),key=lambda s:s['physical_step'])]
    actual_dts=[(b-a)/1e9 for a,b in zip(times,times[1:])]
    actual_tick=[c[0]['physical_step'] for i,c in sorted(byc.items()) if len(c)==1]
    clock={'physics_steps_per_app_update':dict(collections.Counter(deltas)),'callback_dt_s':quantiles(dts),'actual_physics_dt_s':quantiles(actual_dts),
        'source_tick_step_differences':dict(collections.Counter(b-a for a,b in zip(actual_tick,actual_tick[1:]))),
        'timing_condition_qualified':bool(deltas and all(x==1 for x in deltas) and dts and all(abs(x-1/spec['physics_hz'])<2e-9 for x in dts)
            and actual_dts and all(abs(x-1/spec['physics_hz'])<2e-9 for x in actual_dts) and len(actual_tick)==spec['targets']
            and all(b-a==spec['stride'] for a,b in zip(actual_tick,actual_tick[1:]))) }
    complete=len(targets)==spec['targets'] and all(m['C_events']==m['F_events']==1 and m['C_geometry'] is not None for m in metrics)
    input_ok=all(m['input_qualified'] for m in metrics)
    frozen_qualified=len(fdata)==spec['targets'] and all(f['clock_mapping_ok'] and f['native_pose_ok'] and f['native_clock_frozen'] for f in fdata.values())
    def conjunction(values):
        values=list(values)
        return False if any(v is False for v in values) else (True if values and all(v is True for v in values) else None)
    target_provenance_qualified=all(m['event_provenance_ok'] is True and m['clock_mapping_ok'] is True for m in metrics)
    lifecycle_qualified=all(json.loads((parent/name).read_text()).get('cleanup',{}).get('passed') is True for name in ('continuous_terminal.json','frozen_terminal.json'))
    summary={'schema_version':1,'capture_complete':complete,'measurement_qualified':complete and input_ok and ray_qualified and frozen_qualified and clock['timing_condition_qualified'] and target_provenance_qualified,
        'target_provenance_qualified':target_provenance_qualified,
        'lifecycle_qualified':lifecycle_qualified,
        'analyzer_sha256':digest(Path(__file__)),'frozen_clock_pose_qualified':frozen_qualified,
        'timing_condition_qualified':clock['timing_condition_qualified'],'raw_capture_integrity_ok':True,'verified_files':verified,
        'input_qualified':input_ok,'frozen_ray_model_qualified':ray_qualified,'frozen_max_ray_p95_m':max(f_ray,default=None),
        'planned_sensor_targets':spec['targets'],'raw_event_count':len(raw),'unassigned_event_count':len(rows(cdir/'unassigned_events.jsonl')),
        'rejected_event_count':len(rows(cdir/'event_rejections.jsonl')),'failure_crosstable':dict(cross),
        'all_GMO_valid_XYZ_equals_extractor':all(decoded_equal) if decoded_equal else None,'full_gmo_analyzed':len(decoded_equal),
        'native_pose_failed':sum(m['native_pose_ok'] is False for m in metrics),'geometry_failed':sum(m['geometry_ok'] is False for m in metrics),
        'geometry_plane_failed':sum(m['C_geometry'] is not None and not m['C_geometry']['passes_5mm'] for m in metrics),
        'C_max_plane_p95_m':max((m['C_geometry']['point_plane_m']['0.95'] for m in metrics if m['C_geometry']),default=None),
        'C_max_abs_yaw_rad':max((abs(m['C_geometry']['yaw_fit_rad']) for m in metrics if m['C_geometry'] and m['C_geometry']['yaw_fit_rad'] is not None),default=None),
        'candidate_status_counts':dict(collections.Counter(c['status'] for c in component)),
        'best_candidate_group_counts':dict(collections.Counter('|'.join(c['best_members']) for c in component)),
        'clock_mapping_ok':conjunction(m['clock_mapping_ok'] for m in metrics),'event_provenance_ok':conjunction(m['event_provenance_ok'] for m in metrics),
        'gmo_decode_unavailable_count':len(decode_failures),
        'payload_freshness_ok':None,'formal_continuous_acceptance':False,'spec':spec,
        'source_target_table_sha256':digest(cdir/'target_pose_table.jsonl'),'analysis_rules_sha256':digest(parent/'analysis_rules.json')}
    if sum(cross.values())!=spec['targets']:raise ValueError('Planned denominator lost')
    summary['run_qualified']=summary['measurement_qualified'] and lifecycle_qualified
    for name,value in [('summary',summary),('clock_metrics',clock),('planned_target_metrics',metrics),('component_delay',component),('gmo_headers',gmo_headers),('gmo_unavailable',decode_failures)]:save(out/(name+'.json'),value)
    print(json.dumps(summary));return summary


if __name__=='__main__':analyze(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else 'analysis')
