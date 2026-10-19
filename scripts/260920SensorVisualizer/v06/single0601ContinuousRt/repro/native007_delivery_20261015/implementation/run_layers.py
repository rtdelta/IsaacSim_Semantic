"""007 independent collector: native and installed LidarSensor paths."""
import asyncio,hashlib,json,math,os,sys,time,traceback,uuid,struct
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.native_rotation_localization.io import Sink,save
from tools.native_rotation_localization.runtime import ANNOTATORS,E_SETTINGS,WALLS,record,safe,settings

def matrix(yaw):
    c,s=math.cos(yaw),math.sin(yaw)
    return [[c,s,0.,0.],[-s,c,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]

def rss():
    return int(Path('/proc/self/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')

async def run():
    import carb.settings,omni.kit.app,omni.usd,omni.timeline,omni.replicator.core as rep
    from isaacsim.core.simulation_manager import SimulationManager as sm,SimulationEvent,_simulation_manager
    from isaacsim.core.rendering_manager import RenderingManager as rm
    from pxr import Usd,UsdGeom,Sdf,Gf
    spec=json.loads(Path(os.environ['S0601_EXPERIMENT_SPEC']).read_text());out=ROOT/spec['output_relative']/'continuous';out.mkdir(parents=True,exist_ok=False)
    sink=Sink(out,spec['queue_bytes'],spec['disk_bytes']);app=omni.kit.app.get_app();ctx=omni.usd.get_context();tl=omni.timeline.get_timeline_interface();cs=carb.settings.get_settings()
    mapper=_simulation_manager.acquire_simulation_manager_interface();epoch=uuid.uuid4().hex
    callbacks=[];products=[];writers=[];states=[];events=[];table={};offset=None;calibration=[];pre=None;revision=0;update_id=0;observe=False;error=None
    stage=layer=pose=None;seq=0;trace_bytes=0;step_start=None;official_sensor=None;poll_seq=0;poll_payloads={}
    start_ns=int(os.environ['S0601_LAUNCH_MONOTONIC_NS']);deadline=start_ns/1e9+spec['wall_timeout_s']
    result={'schema_version':1,'spec':spec,'source_epoch':epoch,'status':'EXPERIMENT_FAILED','formal_continuous_acceptance':False}
    original={'settings':{k:cs.get(k) for k in [*E_SETTINGS,'/app/settings/fabricDefaultSimPeriodNumerator','/app/settings/fabricDefaultSimPeriodDenominator']},
      'capture':cs.get('/omni/replicator/captureOnPlay'),'fps':tl.get_target_framerate(),'tcps':tl.get_time_codes_per_second(),
      'manual':rm._loop_runner.get_manual_mode(),'step':rm._loop_runner.get_manual_step_size()}
    def event(name,row):
        nonlocal trace_bytes
        trace_bytes+=len(json.dumps(row));
        if trace_bytes>128*1024**2:raise RuntimeError('light trace budget')
        sink.event(name,row)
    def sample(phase,dt):
        m=safe(UsdGeom.Xformable(stage.GetPrimAtPath('/RecoverySensor')).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
        row={'phase':phase,'physical_step':sm.get_num_physics_steps(),'sim_time_s':sm.get_simulation_time(),
          'sim_time_ns':str(round(sm.get_simulation_time()*1e9)),'dt_s':float(dt),'matrix':m,'write_revision':revision,
          'app_update_id':update_id,'monotonic_ns':str(time.monotonic_ns())}
        event('baseline_physics.jsonl',row)
        if phase=='physics_post_actual':states.append(row)
    def on_pre(dt,context=None):
        nonlocal pre,revision,error
        try:
            pre=sm.get_num_physics_steps();sample('physics_pre_before_write',dt)
            step=pre+(offset if offset is not None else 1);row=table.get(step)
            pose.Set(Gf.Matrix4d(row['matrix'] if row else matrix(math.radians(spec['initial_yaw_deg']))));revision+=1
            sample('physics_pre_after_write',dt)
        except Exception as exc:error=str(exc)
    def on_post(dt,context=None):
        nonlocal error
        try:
            if offset is None:calibration.append({'pre_counter':pre,'post_counter':sm.get_num_physics_steps()})
            sample('physics_post_actual',dt)
        except Exception as exc:error=str(exc)
    def fetch(data,name):
        v=[v for k,v in data.items() if k==name or k.startswith(name+'-')]
        if len(v)!=1:raise ValueError('same-event annotator missing/ambiguous '+name)
        return v[0]
    class Writer(rep.Writer):
        version='1.0.0';_version='1.0.0'
        def __init__(self,annotations):self.annotators=annotations
        def write_metadata(self):pass
        def write(self,data):
            nonlocal seq,error
            if not observe:return
            n=seq;seq+=1
            row={'receipt_seq':n,'source_epoch':epoch,'product_path':products[0].path,'sensor_id':'lidar/MyAiry_front',
              'callback_physical_step':sm.get_num_physics_steps(),'callback_monotonic_ns':str(time.monotonic_ns()),
              'app_update_id':update_id,'copy_errors':[],'payload_path':None,'native_event':None}
            try:
                for name in ('IsaacReadSimulationTime','ReferenceTime'):
                    try:row[name]=safe(fetch(data,name))
                    except Exception as exc:row['copy_errors'].append(name+': '+str(exc))
                try:
                    cloud=fetch(data,'IsaacExtractRTXSensorPointCloud');a=cloud['data'];a=a.numpy() if hasattr(a,'numpy') else a
                    if not isinstance(a,np.ndarray) or a.dtype.kind!='f' or a.size%3 or a.nbytes>64*1024**2:raise ValueError('invalid bounded XYZ layout')
                    owned=np.array(a.reshape(-1,3),dtype='<f4',order='C',copy=True);raw=owned.tobytes()
                    row.update(payload_path=sink.submit('payloads/lidar_%06d.xyz'%n,raw),payload_sha256=hashlib.sha256(raw).hexdigest(),
                        shape=list(owned.shape),dtype='<f4',raw_nbytes=len(raw),points=len(owned),producer_shape=list(a.shape))
                    if not np.isfinite(owned).all():row['copy_errors'].append('nonfinite XYZ retained without filtering')
                except (RuntimeError,OverflowError):raise
                except Exception as exc:row['copy_errors'].append('XYZ: '+str(exc))
                try:row['rendered_to_world']=safe(np.asarray(fetch(data,'IsaacExtractRTXSensorPointCloud')['info']['transform']).reshape(4,4))
                except Exception as exc:row['copy_errors'].append('native_pose: '+str(exc))
                try:
                    a=fetch(data,'GenericModelOutput');a=a['data'] if isinstance(a,dict) else a;a=a.numpy() if hasattr(a,'numpy') else a
                    if not isinstance(a,np.ndarray) or a.dtype!=np.uint8 or not 264<=a.nbytes<=64*1024**2:raise ValueError('invalid bounded GMO array')
                    raw=np.array(a,dtype=np.uint8,order='C',copy=True).tobytes()
                    row['native_event']={'packet_path':sink.submit('gmo/gmo_%06d.bin.gz'%n,raw,True),'packet_sha256':hashlib.sha256(raw).hexdigest(),'packet_nbytes':len(raw),'ownership':'owned_cpu'}
                except (RuntimeError,OverflowError):raise
                except Exception as exc:row['copy_errors'].append('GMO: '+str(exc))
                row['copy_completed_monotonic_ns']=str(time.monotonic_ns())
                # All legal bytes already belong to the bounded sink. No quality or history lookup here.
                try:
                    ref=row['ReferenceTime'];nref=int(ref['referenceTimeNumerator']);dref=int(ref['referenceTimeDenominator'])
                    if dref<=0:raise ValueError('invalid ReferenceTime denominator')
                    mapped=float(mapper.get_simulation_time_at_time((nref,dref)))
                    if not math.isfinite(mapped):raise ValueError('nonfinite native mapped time')
                    row['mapped_time_s']=mapped;row['mapped_time_ns']=str(round(mapped*1e9))
                except Exception as exc:row['mapping_error']=str(exc)
                event('raw_events.jsonl',row);events.append(row)
            except Exception as exc:error='native copy/save: '+str(exc)
    def poll_api():
        nonlocal poll_seq,error
        if official_sensor is None or not observe:return
        n=poll_seq;poll_seq+=1
        row={'poll_seq':n,'physical_step_at_read':sm.get_num_physics_steps(),'app_update_id':update_id,
          'read_monotonic_ns':str(time.monotonic_ns()),'source_epoch':epoch,'product_path':products[0].path}
        try:
            a,info=official_sensor.get_data('generic-model-output')
            if a is None:row['status']='empty'
            else:
                a=a.numpy() if hasattr(a,'numpy') else a
                if not isinstance(a,np.ndarray) or a.dtype!=np.uint8 or a.nbytes>64*1024**2:raise ValueError('unqualified API buffer')
                raw=np.array(a,dtype=np.uint8,order='C',copy=True).tobytes()
                if len(raw)<264:row.update(status='empty',owned_nbytes=len(raw))
                else:
                    magic,major,minor,patch,size,count=struct.unpack_from('<IIIIQI',raw)
                    if magic!=0x4e474d4f or (major,minor,patch)!=(1,0,0) or not 264<=size<=len(raw):raise ValueError('API GMO bounds')
                    frame,stamp=struct.unpack_from('<QQ',raw,32);digest=hashlib.sha256(raw).hexdigest()
                    identity=(frame,stamp);key=(*identity,digest)
                    repeated=key in poll_payloads
                    if not repeated:poll_payloads[key]=sink.submit('api_gmo/poll_%06d.bin.gz'%n,raw,True)
                    row.update(status='data',native_frame_id=str(frame),timestamp_ns=str(stamp),packet_sha256=digest,
                        declared_sha256=hashlib.sha256(raw[:size]).hexdigest(),packet_nbytes=len(raw),packet_path=poll_payloads[key],
                        repeated_owned_payload=repeated,info=safe(info))
            row['copy_completed_monotonic_ns']=str(time.monotonic_ns())
        except Exception as exc:row.update(status='error',error=str(exc));error='official API copy: '+str(exc)
        event('api_polls.jsonl',row)
    async def update(phase):
        nonlocal update_id
        update_id+=1;before=sm.get_num_physics_steps();stamp=time.monotonic_ns()
        await app.next_update_async()
        poll_api()
        event('app_updates.jsonl',{'app_update_id':update_id,'phase':phase,'physical_step_before':before,'physical_step_after':sm.get_num_physics_steps(),
          'started_monotonic_ns':str(stamp),'finished_monotonic_ns':str(time.monotonic_ns())})
        if error or sink.error:raise RuntimeError(error or sink.error)
        if time.monotonic()>deadline-30:raise RuntimeError('wall budget including launch; reserved cleanup')
    async def initialize():
        nonlocal stage,layer,pose,offset,official_sensor
        import isaacsim.sensors.experimental.rtx  # Same installed native package initialized before products in P_E.
        cs.set('/app/settings/fabricDefaultSimPeriodNumerator',1);cs.set('/app/settings/fabricDefaultSimPeriodDenominator',60)
        await ctx.new_stage_async();stage=ctx.get_stage();UsdGeom.SetStageMetersPerUnit(stage,1.);UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
        original['stage_tcps']=stage.GetTimeCodesPerSecond();original['edit']=stage.GetEditTarget()
        layer=Sdf.Layer.CreateAnonymous('IndependentInstantRoom.usda');stage.GetSessionLayer().subLayerPaths.insert(0,layer.identifier);stage.SetEditTarget(layer)
        tl.stop();tl.commit();rep.orchestrator.set_capture_on_play(False)
        sensor=stage.DefinePrim('/RecoverySensor','OmniLidar');sensor.GetReferences().AddReference(spec['scene_asset'],spec['source_prim'])
        pose=UsdGeom.Xformable(sensor).MakeMatrixXform();pose.Set(Gf.Matrix4d(1.))
        overrides=[]
        for name,value in spec['sensor_overrides'].items():
            a=sensor.GetAttribute(name);before=a.Get()
            if before is None:raise RuntimeError('missing sensor schema '+name)
            a.Set(value);overrides.append({'name':name,'before':safe(before),'after':safe(a.Get())})
        for name,value in [('omni:sensor:Core:instantLidar',True),('omni:sensor:Core:scanRateBaseHz',10.)]:
            if sensor.GetAttribute(name).Get()!=value:raise RuntimeError('source asset incompatible: '+name)
        channel_attr=sensor.GetAttribute('_replicator:rendervar:GenericModelOutput:channels')
        if not channel_attr or channel_attr.Get() is None:
            channel_attr=sensor.CreateAttribute('_replicator:rendervar:GenericModelOutput:channels',Sdf.ValueTypeNames.StringArray,True)
            channel_attr.Set(['BASIC']);overrides.append({'name':channel_attr.GetName(),'before':None,'after':['BASIC'],'reason':'same native identity channels in both asset/API branches'})
        save(out/'sensor_overrides.json',overrides)
        for w in WALLS:
            cube=UsdGeom.Cube.Define(stage,'/RecoveryRoom/Wall_%d_%s'%(w['axis'],'plus' if w['coordinate_m']>0 else 'minus'));cube.CreateSizeAttr(2.)
            m=np.eye(4);m[:3,:3]=np.diag(w['halfsize_m']);m[3,:3]=w['center_m'];cube.AddTransformOp().Set(Gf.Matrix4d(m.tolist()))
        sm.setup_simulation(dt=1/60);rm.set_dt(1/60)
        for k,v in spec['requested_settings'].items():cs.set(k,v)
        callbacks.extend([sm.register_callback(on_pre,SimulationEvent.PHYSICS_PRE_STEP,order=-100),sm.register_callback(on_post,SimulationEvent.PHYSICS_POST_STEP,order=100)])
        tl.play();tl.commit()
        for _ in range(6):await update('initialization')
        tl.pause();tl.commit();offsets={x['post_counter']-x['pre_counter'] for x in calibration}
        if len(offsets)!=1 or not offsets.issubset({0,1}):raise RuntimeError('PRE/POST semantics unqualified')
        offset=offsets.pop();save(out/'pre_post_counter_qualification.json',{'offset':offset,'samples':calibration})
        if spec.get('api')=='official':
            from isaacsim.sensors.experimental.rtx import Lidar,LidarSensor
            from types import SimpleNamespace
            author=Lidar('/RecoverySensor',accumulate_outputs=None,aux_output_level='BASIC',reset_xform_op_properties=False)
            with Usd.EditContext(stage,layer):official_sensor=LidarSensor(author,annotators=['generic-model-output'])
            product=SimpleNamespace(path=str(official_sensor.render_product.GetPath()),destroy=official_sensor._invalidate_sensor)
        else:
            with Usd.EditContext(stage,layer):product=rep.create.render_product('/RecoverySensor',(300,300),name='S0601_MyAiry_front',force_new=True,write_to_session_layer=False)
        products.append(product);annotations=[]
        for name in ANNOTATORS:
            a=rep.AnnotatorRegistry.get_annotator(name,device='cpu',do_array_copy=True)
            if name=='IsaacReadSimulationTime':a.initialize(resetOnStop=True)
            annotations.append(a)
        writer=Writer(annotations);writers.append(writer);writer.attach([product.path]);rep.orchestrator.set_capture_on_play(True)
    try:
        await asyncio.wait_for(initialize(),spec['init_timeout_s'])
        record(out,stage,'/RecoverySensor',products[0].path,spec,{'initial_physics_updates':6,'static_updates':24,'product_created_at_step':sm.get_num_physics_steps()})
        save(out/'run_spec.json',spec);save(out/'effective_settings_before.json',settings(stage))
        initial_rss=rss();rss_limit=max(4*1024**3,2*initial_rss);save(out/'resource_budget.json',{'rss_limit_bytes':rss_limit,'initial_rss_bytes':initial_rss,'wall_deadline_monotonic_s':deadline})
        observe=True;tl.play();tl.commit()
        for _ in range(24):await update('static_warmup')
        from tools.native_rotation_localization.runtime import capture_settings
        capture_settings(out,stage)
        save(out/'api_topology.json',{'api':spec.get('api','native'),'official_additional_annotators':official_sensor.annotators if official_sensor else [],
            'official_get_data_device':'cuda requested by installed API; owned CPU copy via numpy' if official_sensor else None,
            'comparison_scope':'API plus product/annotator topology; bridge required before API-only attribution' if official_sensor else 'native four-annotator writer',
            'graph_nodes':[{'path':str(p.GetPath()),'type':p.GetTypeName(),
                'connections':{a.GetName():[str(x) for x in a.GetConnections()] for a in p.GetAttributes() if a.GetConnections()}}
                for p in stage.Traverse() if p.GetTypeName() in ('OmniGraph','OmniGraphNode','RenderProduct','RenderVar')]})
        anchors=[]
        for e in events:
            try:
                src=round(float(e['IsaacReadSimulationTime']['simulationTime'])*1e9);mapped=int(e['mapped_time_ns'])
                candidates=[s for s in states if abs(int(s['sim_time_ns'])-src)<=2 and abs(int(s['sim_time_ns'])-mapped)<=2]
                if abs(src-mapped)<=2 and len(candidates)==1:anchors.append(candidates[0]['physical_step'])
            except (KeyError,ValueError,TypeError):pass
        unique=sorted(set(anchors));current=sm.get_num_physics_steps()
        if len(unique)<2 or any(b-a!=6 for a,b in zip(unique,unique[1:])):raise RuntimeError('fixed warmup native tick phase unqualified')
        first=unique[-1]+((current-unique[-1])//6+2)*6;step_start=first-5;last=first+(spec['targets']-1)*6;end=last+12
        coded_yaw=spec['initial_yaw_deg']
        for step in range(step_start,end+1):
            n=step-step_start+1
            if spec.get('motion')=='coded':
                coded_yaw+=(.02,.05,.10)[((17*n+5)%31)%3];yaw=math.radians(coded_yaw)
            else:yaw=math.radians(spec['initial_yaw_deg']+n*spec['yaw_rate_deg_s']/60)
            table[step]={'physical_step':step,'motion_step':n,'matrix':matrix(yaw),'yaw_rad':yaw};event('pose_table.jsonl',table[step])
        save(out/'motion_table_hash.json',{'sha256':hashlib.sha256(json.dumps(table,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'steps':len(table),'frozen_before_motion':True})
        save(out/'planned_targets.json',{'first':first,'last':last,'end':end,'steps':list(range(first,last+1,6)),'start_motion_step':step_start,'warmup_updates':24,'native_anchor_steps':unique,'target_phase_offset_steps':0})
        while sm.get_num_physics_steps()<end:
            await update('motion_and_drain')
            if rss()>rss_limit:raise RuntimeError('RSS budget')
        observe=False;tl.pause();tl.commit();save(out/'effective_settings_after.json',settings(stage))
        result.update(status='EXPERIMENT_COMPLETE',capture_complete=True,raw_events=seq,first_physical_step=first,last_physical_step=last,end_physical_step=sm.get_num_physics_steps())
    except Exception as exc:result.update(capture_complete=False,failure=str(exc),traceback=traceback.format_exc())
    finally:
        observe=False;cleanup={}
        try:
            for w in writers:w.detach()
            writers.clear();rep.orchestrator.set_capture_on_play(False);await asyncio.wait_for(rep.orchestrator.stop_async(),15)
            for p in products:p.destroy()
            products.clear()
            for c in callbacks:sm.deregister_callback(c)
            callbacks.clear();tl.stop();tl.commit()
            if layer:
                stage.GetSessionLayer().subLayerPaths.remove(layer.identifier);stage.SetEditTarget(original['edit']);stage.SetTimeCodesPerSecond(original['stage_tcps'])
            tl.set_time_codes_per_second(original['tcps']);tl.set_target_framerate(original['fps'])
            if original['step']>0:rm._loop_runner.set_manual_step_size(original['step'])
            rm._loop_runner.set_manual_mode(original['manual'])
            for k,v in original['settings'].items():cs.destroy_item(k) if v is None else cs.set(k,v)
            rep.orchestrator.set_capture_on_play(bool(original['capture']));tl.commit()
            cleanup={'writers':len(writers),'products':len(products),'callbacks':len(callbacks),'timeline_stopped':not tl.is_playing(),
              'settings_restored':all(cs.get(k)==v for k,v in original['settings'].items()),'timeline_restored':tl.get_time_codes_per_second()==original['tcps'] and tl.get_target_framerate()==original['fps'],
              'session_layer_removed':not layer or layer.identifier not in stage.GetSessionLayer().subLayerPaths}
            cleanup['passed']=not writers and not products and not callbacks and all(cleanup[k] for k in ('timeline_stopped','settings_restored','timeline_restored','session_layer_removed'))
        except Exception as exc:cleanup.update(passed=False,error=str(exc))
        result['cleanup']=cleanup;result['finished_monotonic_ns']=str(time.monotonic_ns())
        if not cleanup['passed']:result.update(status='EXPERIMENT_FAILED',failure_kind='cleanup')
        save(out/'cleanup.json',cleanup);save(out/'run_result.json',result)
        try:
            await asyncio.to_thread(sink.close)
            from tools.native_rotation_localization.official_crosscheck import check
            save(out.parent/'official_parser_crosscheck.json',check(out))
        except Exception as exc:result.update(status='EXPERIMENT_FAILED',save_failure=str(exc))
        save(out.parent/'continuous_terminal.json',result)
        app.post_uncancellable_quit(0 if result['status']=='EXPERIMENT_COMPLETE' else 2)
asyncio.ensure_future(run())
