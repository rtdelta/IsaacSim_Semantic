"""One native run_async scenario. No per-group step_async or six-step schedule.

NVIDIA owns subframe pacing and publication. Event/counter reads are diagnostic;
the BasicWriter PNGs are an independent, native final-capture reference.
"""
import asyncio,hashlib,json,math,time

async def run_continuous(app,ctx,timeline,stage,sensors,products,art,initial,indices,names,settings,out,spec,event):
 import numpy as np
 import carb.eventdispatcher
 import omni.replicator.core as rep
 from omni.replicator.core.scripts import orchestrator as sdk
 from pxr import UsdGeom
 from isaacsim.core.simulation_manager import SimulationManager

 total=int(spec['pt_total_spp']);spp=int(spec['pt_spp']);count=int(spec['measure_frames'])
 if total<1 or spp<1 or total%spp:raise ValueError('PT total must be a positive multiple of per-iteration SPP')
 if settings.get('/rtx/rendermode')!='PathTracing':raise RuntimeError('PathTracing is required')
 settings.set('/rtx/resetPtAccumOnAnimTimeChange',True)
 settings.set('/rtx/pathtracing/adaptiveSampling/enabled',False)
 settings.set('/omni/replicator/RTSubframes',1)
 rep.orchestrator.set_capture_on_play(False)
 observers={};clouds={};time_observers={}
 camera_indices=[i for i,s in enumerate(sensors) if s['kind']=='camera']
 for i in camera_indices:
  rgb=rep.AnnotatorRegistry.get_annotator('rgb');rgb.attach([products[i].path])
  params=rep.AnnotatorRegistry.get_annotator('CameraParams');params.attach([products[i].path]);observers[i]=(rgb,params)
 for i,s in enumerate(sensors):
  clock_ann=rep.AnnotatorRegistry.get_annotator('IsaacReadSimulationTime');clock_ann.attach([products[i].path]);time_observers[i]=clock_ann
  if s['kind']=='lidar':
   ann=rep.AnnotatorRegistry.get_annotator('IsaacExtractRTXSensorPointCloud',device='cpu',do_array_copy=True)
   ann.attach([products[i].path]);clouds[i]=ann
 if spec.get('native_preview_initialization',False):
  event('native_preview_begin')
  await rep.orchestrator.preview_async()
  for _ in range(2):await app.next_update_async()
  event('native_preview_end',native_time=SimulationManager.get_simulation_time())
 writer=rep.WriterRegistry.get('BasicWriter')
 writer.initialize(output_dir=str(out/'native_basic_images'),rgb=spec.get('extra_capture_png',True),camera_params=True,use_common_output_dir=False,frame_padding=4)
 writer.attach([products[i] for i in camera_indices])
 snapshots=[];rows=[];updates=[];errors=[];cycles=[];scheduled=[];current=None
 reference=next(p for p in stage.Traverse() if p.GetName()=='NativeReferenceFrame')
 joint_targets=[0.,0.,0.,0.]  # NC004: identical static pose for all configurations.

 def sample_pose():
  cache=UsdGeom.XformCache();base=cache.GetLocalToWorldTransform(reference)
  expected={};world={}
  for s in sensors:
   world[s['frame_id']]=np.asarray(cache.GetLocalToWorldTransform(stage.GetPrimAtPath(s['prim_path']))).tolist()
   m=cache.GetLocalToWorldTransform(stage.GetPrimAtPath(s['tf_prim_path']))*base.GetInverse();q=m.ExtractRotationQuat().GetNormalized()
   expected[s['frame_id']]={'parent':'swing_coordinate','translation':list(m.ExtractTranslation()),'quaternion_xyzw':[*q.GetImaginary(),q.GetReal()]}
  q=base.ExtractRotationQuat().GetNormalized();expected['swing_coordinate']={'parent':'world','translation':list(base.ExtractTranslation()),'quaternion_xyzw':[*q.GetImaginary(),q.GetReal()]}
  values=art.get_dof_positions().numpy()
  return {'expected_tf':expected,'world':world,'joints_rad':{n:float(values[0,j]) for n,j in zip(names,indices)}}

 def on_native(e):
  nonlocal current
  try:
   payload=e.payload if hasattr(e,'payload') else e
   if 'trigger' in payload:
    index=len(cycles)
    if index>=count:return
    pos=initial.copy()
    for j in indices:pos[0,j]=0.
    if indices:pos[0,indices[0]]=np.deg2rad(joint_targets[index%len(joint_targets)])
    art.set_dof_positions(pos);art.set_dof_velocities(np.zeros_like(pos))
    ctx.reset_renderer_accumulation()
    current={'index':index,'begin_ns':time.monotonic_ns(),'thread_cpu_begin':time.thread_time_ns(),
     'sdk_trigger_time':list(payload['trigger']),'begin_sim_time':SimulationManager.get_simulation_time(),
     'target_boom_deg':joint_targets[index%len(joint_targets)],'reset_accumulation':True,
     'requested_total_spp':total,'requested_spp_per_iteration':spp,'expected_native_subframes':total//spp,'updates':[]}
    cycles.append(current);event('native_frame_begin',**{k:v for k,v in current.items() if k!='updates'})
   if 'capture' in payload:
    if current is None:raise RuntimeError('Capture event without logical frame trigger')
    current.update(capture_ns=time.monotonic_ns(),native_time_s=SimulationManager.get_simulation_time(),
     sdk_capture_time=[list(x) for x in payload['capture']],sdk_subframes_at_capture=int(sdk._orchestrator._subframe),
     effective_quality={k:settings.get(k) for k in ('/rtx/rendermode','/rtx/pathtracing/spp','/rtx/pathtracing/totalSpp','/rtx/pathtracing/maxBounces','/rtx/pathtracing/adaptiveSampling/enabled','/rtx/resetPtAccumOnAnimTimeChange','/rtx/pathtracing/optixDenoiser/enabled')},
     **sample_pose())
    scheduled.append(current)
    event('native_frame_scheduled',group=current['index'],native_time=current['native_time_s'],
     native_subframes=current['sdk_subframes_at_capture'],requested_total_spp=total)
  except Exception as exc:
   errors.append(type(exc).__name__+': '+str(exc));event('native_observer_error',error=errors[-1])

 subscription=carb.eventdispatcher.get_eventdispatcher().observe_event(event_name=sdk.ORCHESTRATOR_EVENT,on_event=on_native,observer_name='NC003:native-frame-evidence')
 timeline.set_auto_update(True);timeline.play();timeline.commit()
 scenario_start=time.monotonic_ns();start_cpu=time.thread_time_ns()
 try:
  await rep.orchestrator.run_async(num_frames=count,start_timeline=False)
  event('native_continuous_started',frames=count,total_spp=total,spp=spp,native_subframes=total//spp)
  last_observed=0
  while not rep.orchestrator.get_is_stopped():
   if (out/'stop.request').exists():rep.orchestrator.stop()
   a=time.monotonic_ns();cpu=time.thread_time_ns();before=SimulationManager.get_simulation_time()
   await app.next_update_async()
   after=SimulationManager.get_simulation_time()
   u={'start_ns':a,'end_ns':time.monotonic_ns(),'thread_cpu_ns':time.thread_time_ns()-cpu,
      'simulation_before_s':before,'simulation_after_s':after,'sdk_frame':int(sdk._orchestrator._frame),
      'sdk_subframe_after_update':int(sdk._orchestrator._subframe),'sdk_captured_frames':int(sdk._orchestrator._num_captured_frames),
      'status':str(rep.orchestrator.get_status())}
   updates.append(u)
   with (out/'native_updates.jsonl').open('a') as f:f.write(json.dumps(u)+'\n')
   if current:current['updates'].append(u)
   observed=int(writer._frame_id)  # Installed BasicWriter diagnostic completion counter only.
   if observed>last_observed:
    if observed-last_observed!=1:raise RuntimeError('BasicWriter observer missed an intermediate completed frame')
    index=observed-1
    if index>=len(scheduled):raise RuntimeError('BasicWriter completed before native capture schedule evidence')
    g=scheduled[index];evidence={};lidar_evidence={};read_start=time.monotonic_ns()
    for i,(ann,params) in observers.items():
     rgb=np.ascontiguousarray(np.asarray(ann.get_data())[:,:,:3]);cp=params.get_data()
     world=np.linalg.inv(np.asarray(cp['cameraViewTransform']).reshape(4,4))
     evidence[sensors[i]['topic']]={'sha256':hashlib.sha256(rgb.tobytes()).hexdigest(),'shape':list(rgb.shape),
      'camera_pose_max_abs_error':float(np.max(np.abs(world-np.asarray(g['world'][sensors[i]['frame_id']])))),'native_basic_writer_frame':index}
    for i,ann in clouds.items():
     d=ann.get_data();raw=d['data'];xyz=raw.numpy() if hasattr(raw,'numpy') else np.asarray(raw)
     xyz=np.ascontiguousarray(xyz,dtype='<f4').reshape(-1,3)
     lidar_evidence[sensors[i]['topic']]={'points':len(xyz),'sha256_xyz':hashlib.sha256(xyz.tobytes()).hexdigest(),
      'render_pose_max_abs_error':float(np.max(np.abs(np.asarray(d['info']['transform']).reshape(4,4)-np.asarray(g['world'][sensors[i]['frame_id']]))))}
    end=time.monotonic_ns();budget=g['sdk_subframes_at_capture']==total//spp
    native_times={sensors[i]['topic']:d.get_data() for i,d in time_observers.items()}
    native_times={k:float(v['simulationTime'] if isinstance(v,dict) else np.asarray(v).reshape(-1)[0]) for k,v in native_times.items()}
    row={'frame':index,'group':index,'case':{'name':'native_continuous_pt'+str(total),'renderer':'PathTracing','total_spp':total,'pose':'joint_'+str(g['target_boom_deg'])},
     'start_ns':g['begin_ns'],'end_ns':read_start,'inclusive_thread_cpu_ns':time.thread_time_ns()-g['thread_cpu_begin'],
     'native_time_s':g['native_time_s'],'native_time_after_s':after,'native_sensor_times_s':native_times,'images':evidence,'lidars':lidar_evidence,
     'joints_rad':g['joints_rad'],'expected_tf':g['expected_tf'],'requested_pt_total_spp':total,
     'sdk_subframes_at_capture':g['sdk_subframes_at_capture'],'budget_gate_passed':budget,'accumulation_reset':g['reset_accumulation'],
     'native_frame_scheduled_s':(g['capture_ns']-g['begin_ns'])/1e9,'capture_to_observation_s':(read_start-g['capture_ns'])/1e9,
     'payload_observed_scope_s':(end-g['begin_ns'])/1e9,'evidence_s':(end-read_start)/1e9,
     'schedule':'single native run_async','diagnostic_native_gate_bypass':False,'quality_png_exported':spec.get('extra_capture_png',True), 'diagnostic_basic_writer':'CameraParams only' if not spec.get('extra_capture_png',True) else 'RGB+CameraParams',
     'settings':g['effective_quality'],'limits':'Native subframe/budget completion, not a hardware ray counter.'}
    rows.append(row)
    with (out/'groups.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
    event('native_frame_observed',group=index,native_time=g['native_time_s'],budget_gate_passed=budget,wall_s=row['payload_observed_scope_s'])
    last_observed=observed
   if errors:raise RuntimeError('; '.join(errors))
  await rep.orchestrator.wait_until_complete_async()
  if len(rows)!=count:raise RuntimeError(f'Incomplete native capture: observed {len(rows)} of {count}')
  if not all(r['budget_gate_passed'] and r['accumulation_reset'] for r in rows):raise RuntimeError('Per-frame PT budget/reset evidence failed')
  # Capture event and renderer output are distinct; preserve both timestamps.
  for g in cycles:
   g.pop('world',None)
  (out/'native_cycles.json').write_text(json.dumps(cycles,indent=2))
  (out/'continuous_result.json').write_text(json.dumps({'frames':len(rows),'app_updates':len(updates),
   'native_scenario_wall_s':(time.monotonic_ns()-scenario_start)/1e9,'inclusive_thread_cpu_s':(time.thread_time_ns()-start_cpu)/1e9,
   'budget_all_frames_passed':True,'native_single_run':True,'settings':rows[-1]['settings'],
   'limits':['SPP is verified requested renderer budget plus native scheduling completion, not exact hardware ray count.','BasicWriter completion and SDK counters are diagnostic; ROS messages and MCAP serializers are unchanged.']},indent=2))
  return rows
 finally:
  subscription.reset()
