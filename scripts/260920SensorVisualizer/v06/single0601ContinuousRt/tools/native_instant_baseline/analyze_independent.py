"""Offline-only source association and independent absolute/increment geometry."""
import collections,gzip,hashlib,json,math,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT.parent)]
from tools.native_instant_baseline.io import rows,save,verify,sha
from tools.native_instant_baseline.math_independent import decode,ranges,geometry,yaw,pose,difference,wrap,quantiles,classify

def conjunction(values):
    values=list(values)
    return False if False in values else (None if not values or None in values else True)

def analyze(parent):
    parent=Path(parent);c=parent/'continuous';out=parent/'analysis';out.mkdir(exist_ok=False)
    spec=json.loads((parent/'run_spec.json').read_text());planned=json.loads((c/'planned_targets.json').read_text())
    terminal=json.loads((parent/'continuous_terminal.json').read_text());verified=verify(c)
    physics=rows(c/'baseline_physics.jsonl');post=[r for r in physics if r['phase']=='physics_post_actual']
    bystep=collections.defaultdict(list)
    for r in post:bystep[r['physical_step']].append(r)
    states={k:v[0]['matrix'] for k,v in bystep.items() if len(v)==1};ns={k:int(v[0]['sim_time_ns']) for k,v in bystep.items() if len(v)==1}
    raw=rows(c/'raw_events.jsonl') if spec['group'].startswith('M') else rows(c/'raw_receipts.jsonl')
    assoc={r['receipt_seq']:r for name in ('native_events.jsonl','unassigned_events.jsonl') for r in rows(c/name)}
    target_events=collections.defaultdict(list);associations=[];decoded_events={};errors=[];full_decode=0
    params=json.loads((c/'sensor_manifest.json').read_text())['attributes']
    def setting(name):return params[name]['value']
    model_ok=all(not np.any(np.asarray(setting('omni:sensor:Core:emitterState:s001:'+n))) for n in ('horOffsetM','vertOffsetM','distanceCorrectionM','fireTimeNs'))
    az=np.deg2rad(np.asarray(setting('omni:sensor:Core:emitterState:s001:azimuthDeg'),float));el=np.deg2rad(np.asarray(setting('omni:sensor:Core:emitterState:s001:elevationDeg'),float))
    nominal=np.column_stack((np.cos(el)*np.cos(az),-np.cos(el)*np.sin(az),np.sin(el)))
    all_native_steps=[]
    for r in raw:
        number=r['receipt_seq'];reasons=[];source=mapped=None;chosen=None
        try:
            value=float(r['IsaacReadSimulationTime']['simulationTime'])
            if not math.isfinite(value):raise ValueError('nonfinite source')
            source=round(value*1e9);mapped=int(r.get('mapped_time_ns',assoc.get(number,{}).get('mapped_time_ns')))
            candidates_source=[k for k,t in ns.items() if abs(t-source)<=2];candidates_ref=[k for k,t in ns.items() if abs(t-mapped)<=2]
            if len(candidates_source)==1 and candidates_source==candidates_ref and abs(source-mapped)<=2:chosen=candidates_source[0]
            else:reasons.append('source/reference not uniquely the same physical step')
        except Exception as exc:candidates_source=[];candidates_ref=[];reasons.append('time: '+str(exc))
        entry={'receipt_seq':number,'source_time_ns':str(source) if source is not None else None,'mapped_time_ns':str(mapped) if mapped is not None else None,
          'source_candidate_steps':candidates_source,'reference_candidate_steps':candidates_ref,'physical_step':chosen,'reasons':reasons,'copy_errors':r.get('copy_errors',[])}
        if chosen is not None:target_events[chosen].append(r);all_native_steps.append(chosen)
        associations.append(entry)
        try:
            p=c/r['payload_path'];b=p.read_bytes()
            if hashlib.sha256(b).hexdigest()!=r['payload_sha256'] or len(b)!=r['raw_nbytes']:raise ValueError('XYZ SHA/size')
            xyz=np.frombuffer(b,dtype='<f4').reshape(r['shape'])
            if not np.isfinite(xyz).all():raise ValueError('nonfinite XYZ retained')
            metadata=r['native_event'];p=c/metadata['packet_path'];b=gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes()
            if hashlib.sha256(b).hexdigest()!=metadata['packet_sha256'] or len(b)!=metadata['packet_nbytes']:raise ValueError('GMO SHA/size')
            header,arrays,allxyz=decode(b);valid=(arrays['flags']&64)!=0
            if not np.array_equal(allxyz[valid],xyz):raise ValueError('valid-flag GMO/Extractor order/value mismatch')
            if any(k not in arrays for k in ('emitter_id','channel_id','tick_id','echo_id')):raise ValueError('native ray identities unavailable')
            ids=np.column_stack([arrays[k][valid] for k in ('emitter_id','channel_id','tick_id','echo_id')])
            if len(np.unique(ids,axis=0))!=len(xyz):raise ValueError('duplicate native ray identities')
            ray=nominal[arrays['emitter_id'][valid]];dist=np.linalg.norm(xyz.astype(float),axis=1)
            # The old ABI decoder is a cross-check only, never the primary coordinate oracle.
            from tools.experiments.decode_gmo import decode as legacy_decode
            oldhead,oldarr,oldaux,oldxyz=legacy_decode(b)
            if not np.array_equal(allxyz,oldxyz) or any(not np.array_equal(arrays[k],oldarr[k]) for k in ('flags','emitter_id','channel_id','tick_id','echo_id')):raise ValueError('independent/legacy GMO decode disagreement')
            full_decode+=1
            decoded_events[number]=(xyz,ray,dist,header,{'raw_count':len(allxyz),'invalid_count':int((~valid).sum()),'valid_count':len(xyz),'unique_native_ids':len(ids)})
        except Exception as exc:errors.append({'receipt_seq':number,'reason':str(exc)})
    updates=rows(c/'app_updates.jsonl');active=[u for u in updates if u['phase']=='motion_and_drain']
    update_ok=bool(active) and all(u['physical_step_after']-u['physical_step_before']==1 for u in active)
    active_steps=list(range(planned['start_motion_step'],planned['end']+1))
    dt_ok=all(k in ns and k-1 in ns and abs((ns[k]-ns[k-1])-1e9/60)<=2 and abs(bystep[k][0]['dt_s']-1/60)<=2e-9 for k in active_steps)
    ticks=sorted(all_native_steps);tick_ok=len(ticks)>=2 and len(set(ticks))==len(ticks) and all(b-a==6 for a,b in zip(ticks,ticks[1:]))
    angle_step=math.radians(spec['yaw_rate_deg_s'])/60;input_rows=[]
    for step in active_steps:
        y=math.radians(spec['initial_yaw_deg'])+(step-planned['start_motion_step']+1)*angle_step
        if step not in states or step-1 not in states:input_rows.append({'step':step,'ok':False});continue
        pe,re=difference(states[step],pose(y));increment=wrap(yaw(states[step])-yaw(states[step-1]))-angle_step
        input_rows.append({'step':step,'position_error_m':pe,'rotation_error_rad':re,'physical_increment_error_rad':float(increment),'ok':pe<=1e-5 and re<=1e-6 and abs(increment)<=2e-6})
    input_ok=all(r['ok'] for r in input_rows) and len(input_rows)==len(active_steps)
    metrics=[];cross=collections.Counter();legacy_deltas=[]
    from tools.experiments.compare_paired_outputs import geometry as legacy_geometry
    from tools.experiments.analyze_mechanism_relations import ray_ranges as legacy_ranges
    walls=json.loads((c/'scene_manifest.json').read_text())['walls']
    for i,step in enumerate(planned['steps']):
        events=target_events.get(step,[]);m={'target_index':i,'physical_step':step,'motion_step':step-planned['start_motion_step']+1,'event_count':len(events),
          'clock_ok':len(events)==1,'native_pose_ok':None,'geometry_absolute_ok':None,'actual_yaw_rad':yaw(states[step]) if step in states else None}
        if len(events)==1 and step in states:
            event=events[0];m['receipt_seq']=event['receipt_seq'];m['source_time_ns']=str(round(float(event['IsaacReadSimulationTime']['simulationTime'])*1e9))
            try:
                pe,re=difference(states[step],event['rendered_to_world']);m.update(native_position_error_m=pe,native_rotation_error_rad=re,native_pose_ok=pe<=.001 and re<=1e-4)
            except Exception as exc:m['native_pose_error']=str(exc)
            if event['receipt_seq'] in decoded_events:
                xyz,ray,dist,header,counts=decoded_events[event['receipt_seq']];g=geometry(xyz,states[step]);pred=ranges(ray,states[step]);ray_error=quantiles(abs(pred-dist))
                candidate=classify(ray,dist,states,step);m.update(geometry=g,ray_residual_m=ray_error,candidate=candidate,native_header=header,counts=counts,
                  geometry_absolute_ok=conjunction([ray_error['0.95']<=1e-5,g['point_plane_m']['0.95']<=.005,abs(g['yaw_error_rad'])<=1e-4 if g['yaw_error_rad'] is not None else None]),
                  geometry_yaw_rad=m['actual_yaw_rad']+g['yaw_error_rad'] if g['yaw_error_rad'] is not None else None,
                  descriptive_equivalent_lag_steps=-g['yaw_error_rad']/angle_step if angle_step and g['yaw_error_rad'] is not None else None)
                lg=legacy_geometry(xyz,states[step],walls);ld=float(np.max(abs(pred-legacy_ranges(ray,states[step],walls))))
                legacy_deltas.append({'target_index':i,'range_max_difference_m':ld,'plane_p95_difference_m':g['point_plane_m']['0.95']-lg['point_plane_m']['0.95'],
                    'yaw_difference_rad':g['yaw_error_rad']-lg['yaw_fit_rad'] if g['yaw_error_rad'] is not None and lg['yaw_fit_rad'] is not None else None})
        cross['/'.join('unknown' if m[k] is None else ('pass' if m[k] else 'fail') for k in ('clock_ok','native_pose_ok','geometry_absolute_ok'))]+=1;metrics.append(m)
    increments=[]
    for a,b in zip(metrics,metrics[1:]):
        ia=wrap(b['actual_yaw_rad']-a['actual_yaw_rad'])-angle_step*6 if a['actual_yaw_rad'] is not None and b['actual_yaw_rad'] is not None else None
        ga=wrap(b['geometry_yaw_rad']-a['geometry_yaw_rad'])-angle_step*6 if a.get('geometry_yaw_rad') is not None and b.get('geometry_yaw_rad') is not None else None
        increments.append({'target_pair':[a['target_index'],b['target_index']],'input_increment_error_rad':ia,'input_increment_ok':abs(ia)<=2e-6 if ia is not None else None,
            'geometry_increment_error_rad':ga,'geometry_increment_ok':abs(ga)<=1e-4 if ga is not None else None})
    agreement=all(d['range_max_difference_m']<=1e-10 and abs(d['plane_p95_difference_m'])<=1e-10 and (d['yaw_difference_rad'] is None or abs(d['yaw_difference_rad'])<=1e-10) for d in legacy_deltas)
    intact=not errors and all(not r.get('copy_errors') for r in raw) and len(metrics)==spec['targets'] and all(r['event_count']==1 and 'geometry' in r for r in metrics)
    is_static=spec['yaw_rate_deg_s']==0
    static_own=conjunction([model_ok,agreement,intact,*[m.get('ray_residual_m',{}).get('0.95',math.inf)<=1e-5 and m.get('geometry',{}).get('yaw_error_rad') is not None for m in metrics]]) if is_static else None
    suite=ROOT/'reports/native_instant_baseline'/spec['experiment_id'];qual=suite/'qualification_status.json'
    prerequisites=json.loads(qual.read_text()).get(spec['group'],{}).get('static_model_qualified') if qual.exists() else None
    associations_ok=bool(associations) and all(a['physical_step'] is not None and not a['reasons'] for a in associations)
    measurement=conjunction([update_ok,dt_ok,tick_ok,input_ok,model_ok,intact,agreement,associations_ok,static_own if is_static else prerequisites,*[r['input_increment_ok'] for r in increments]])
    summary={'schema_version':1,'spec':spec,'capture_complete':terminal['status']=='EXPERIMENT_COMPLETE','measurement_qualified':measurement,
       'pair_equivalence_qualified':None,'clock_ok':conjunction(m['clock_ok'] for m in metrics),'native_pose_ok':conjunction(m['native_pose_ok'] for m in metrics),
       'geometry_absolute_ok':conjunction(m['geometry_absolute_ok'] for m in metrics),'geometry_increment_ok':conjunction(r['geometry_increment_ok'] for r in increments),
       'payload_generation_freshness':None,'cleanup_ok':terminal.get('cleanup',{}).get('passed'),'formal_continuous_acceptance':False,
       'planned_targets':spec['targets'],'planned_adjacent_pairs':spec['targets']-1,'raw_events':len(raw),'target_missing':sum(m['event_count']==0 for m in metrics),
       'target_duplicate':sum(m['event_count']>1 for m in metrics),'unassigned_events':sum(a['physical_step'] is None for a in associations),
       'outside_target_events':sum(a['physical_step'] is not None and a['physical_step'] not in planned['steps'] for a in associations),
       'native_pose_failed':sum(m['native_pose_ok'] is False for m in metrics),'geometry_absolute_failed':sum(m['geometry_absolute_ok'] is False for m in metrics),
       'geometry_absolute_unknown':sum(m['geometry_absolute_ok'] is None for m in metrics),'geometry_increment_failed':sum(r['geometry_increment_ok'] is False for r in increments),
       'geometry_increment_unknown':sum(r['geometry_increment_ok'] is None for r in increments),'cross_table':dict(cross),'static_model_qualified':static_own,
       'candidate_counts':dict(collections.Counter('|'.join(m.get('candidate',{}).get('best_members',[])) for m in metrics)),
       'progression_checks':{'single_step_per_update':update_ok,'physical_dt':dt_ok,'native_tick_stride':tick_ok,'input':input_ok,'all_events_unique_time_association':associations_ok},
       'readback':{'verified_files':verified,'full_GMO_independently_decoded':full_decode,'errors':errors,'independent_legacy_geometry_agree':agreement},
       'absolute_yaw_rad':quantiles([m['geometry']['yaw_error_rad'] for m in metrics if m.get('geometry',{}).get('yaw_error_rad') is not None]),
       'adjacent_yaw_increment_error_rad':quantiles([r['geometry_increment_error_rad'] for r in increments if r['geometry_increment_error_rad'] is not None]),
       'first_target':metrics[0],'analyzer_sha256':sha(Path(__file__))}
    summary['diagnostic_pass']=conjunction(summary[k] for k in ('capture_complete','measurement_qualified','clock_ok','native_pose_ok','geometry_absolute_ok','geometry_increment_ok','cleanup_ok'))
    for name,data in [('summary',summary),('target_events',associations),('target_metrics',metrics),('adjacent_increments',increments),('input_checks',input_rows),('independent_crosscheck',legacy_deltas)]:save(out/(name+'.json'),data)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('spec','first_target')}));return summary

if __name__=='__main__':analyze(sys.argv[1])
