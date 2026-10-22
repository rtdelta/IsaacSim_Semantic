"""Real Isaac lifecycle/position tests using public project APIs, without OS input injection."""
import asyncio
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from single0602_headless.contracts import write_json
from single0602_headless.interactive_runtime import InteractiveRuntime
from single0602_headless.trajectory import Trajectory

async def main():
    import omni.kit.app
    from isaacsim.core.simulation_manager import SimulationEvent
    from pxr import Gf,UsdGeom
    tag=os.environ.get('S0602_TEST_TAG','continuous_acceptance')
    path=ROOT/'reports'/(tag+'.json')
    output=Path('/root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless/validation')/(tag+'_'+uuid.uuid4().hex[:8])
    report={'state':'running','tag':tag,'output':str(output),'coordinate_cases':[]}
    write_json(path,report)
    runtime=None;witness_callback=None;timing_subscription=None
    try:
        app=omni.kit.app.get_app()
        report['loop_api']={'app_methods':[n for n in dir(app) if 'loop' in n.lower()]}
        if hasattr(app,'get_loop_runner_interface'):
            loop=app.get_loop_runner_interface()
            report['loop_api']['methods']={n:str(getattr(loop,n).__doc__)[:1800] for n in dir(loop) if 'manual' in n.lower()}
        socket=Path('/root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless/runtime')/('t_'+uuid.uuid4().hex[:8]+'.sock')
        runtime=InteractiveRuntime(ROOT,output=output,socket_path=socket,job_path=ROOT/'config/interactive.json')
        await runtime.initialize(open_scene=True)
        import carb.settings
        settings=carb.settings.get_settings()
        report['native_timing']={'manual_mode':runtime.scene.loop_runner.get_manual_mode(),
            'fixed_dt':settings.get('/app/player/useFixedTimeStepping'),
            'min_frame_rate':settings.get('/persistent/simulation/minFrameRate'),
            'async_rendering':settings.get('/app/asyncRendering')}
        timing=[];last=[time.monotonic(),runtime.scene.native_time(),runtime.scene.timeline.get_current_time()]
        def timing_probe(event):
            now=[time.monotonic(),runtime.scene.native_time(),runtime.scene.timeline.get_current_time()]
            timing.append({'app_dt':event.payload['dt'],'wall_dt':now[0]-last[0],
                'native_dt':now[1]-last[1],'timeline_dt':now[2]-last[2]})
            last[:]=now
            if len(timing)>24:del timing[0]
        timing_subscription=runtime.scene.app.get_update_event_stream().create_subscription_to_pop(timing_probe,name='S0602 timing probe')
        def cmd(action,payload=None):
            result=runtime.command({'action':action,'payload':payload or {},'command_id':uuid.uuid4().hex,'accepted_ns':time.monotonic_ns()})
            assert not runtime.failed,runtime.error
            return result
        async def steps(count):
            target=runtime.clock.step_index+count;deadline=time.monotonic()+10
            while runtime.clock.step_index<target:
                assert not runtime.failed,runtime.error
                assert time.monotonic()<deadline,('step timeout',runtime.lifecycle,runtime.error)
                await runtime.scene.app.next_update_async()
        async def rebound():
            deadline=time.monotonic()+15
            while runtime.binding_pending:
                assert not runtime.failed,runtime.error
                assert time.monotonic()<deadline,'binding timeout'
                await runtime.scene.app.next_update_async()
        def keys(values,epoch=None):
            return cmd('keys',{'source':'web:acceptance','keys':values,
                'input_epoch':runtime.keyboard.input_epoch if epoch is None else epoch,
                'sequence':runtime.keyboard.sequences.get('web:acceptance',0)+1})
        velocity_max=0.;position_error_max=0.;joint_error_max=0.
        def check_pose():
            nonlocal velocity_max,position_error_max,joint_error_max
            motion=runtime.scene.motion
            linear,angular=motion.articulation.get_velocities()
            dof=motion.articulation.get_dof_velocities()
            speed=max(abs(float(v)) for array in (linear,angular,dof) for row in array.numpy() for v in row)
            velocity_max=max(velocity_max,speed);assert speed<1e-8,speed
            snap=motion.snapshot(runtime.scene.native_time())
            error=max(abs(a-b) for a,b in zip(snap['root_position'],motion.base_controller.position))
            position_error_max=max(position_error_max,error);assert error<1e-5,error
            actual=motion.actual_degrees()
            error=max(abs(actual[n]-s.angle) for n,s in motion.controller.states.items())
            joint_error_max=max(joint_error_max,error);assert error<1e-4,error
        witness={'steps':0}
        transform=UsdGeom.Xform.Define(runtime.scene.stage,'/S0602ContinuousWitness').AddTranslateOp()
        def witness_step(dt,context):
            witness['steps']+=1;transform.Set(Gf.Vec3d(witness['steps']*.001,0,0))
        witness_callback=runtime.scene.manager.register_callback(witness_step,SimulationEvent.PHYSICS_POST_STEP,order=2000)
        first=cmd('record_start')['path'];cmd('play');await steps(6)
        assert runtime.scene.timeline.is_playing()
        for index in range(20):
            cmd('keyboard',{'enabled':True});keys(['W']);await steps(2);check_pose()
            old_epoch=runtime.keyboard.input_epoch
            cmd('keyboard',{'enabled':False})
            before=deepcopy(runtime.state);before_witness=witness['steps']
            await steps(2);check_pose()
            assert runtime.state['t_sim_s']>before['t_sim_s']
            assert witness['steps']>before_witness
            assert max(abs(a-b) for a,b in zip(before['position_world_m'],runtime.state['position_world_m']))<1e-5
            cmd('keyboard',{'enabled':True})
            try:keys(['W'],old_epoch)
            except ValueError:pass
            else:raise AssertionError('stale epoch accepted')
            assert str(runtime.recorder.directory)==first
        report['toggle_rounds']=20
        for heading in (0,90,180,-90):
            cmd('motion',{'base':{'x':0.,'y':0.,'z':5.,'yaw_deg':heading},
                'tilt':{name:{'mode':'direct','target':value} for name,value in (('pitch',20.),('roll',-15.))}})
            before=deepcopy(runtime.state);keys(['W']);await steps(8);keys([]);check_pose()
            dt=runtime.time_s-before['t_sim_s'];expected=[.5*dt*math.cos(math.radians(heading)),.5*dt*math.sin(math.radians(heading)),0.]
            delta=[a-b for a,b in zip(runtime.state['position_world_m'],before['position_world_m'])]
            error=max(abs(a-b) for a,b in zip(delta,expected));assert error<2e-5,(heading,error,delta,expected)
            report['coordinate_cases'].append({'heading':heading,'dt':dt,'max_error_m':error})
        # Pausing keeps the same file and time. Native panel Play resumes it.
        keys(['W']);await steps(2);cmd('pause')
        paused_time=runtime.time_s;native_time=runtime.scene.native_time();paused_rows=runtime.recorder.count
        for _ in range(8):await runtime.scene.app.next_update_async()
        assert runtime.time_s==paused_time and runtime.scene.native_time()==native_time
        assert runtime.recorder.count==paused_rows
        runtime.scene.timeline.play();runtime.scene.timeline.commit();await steps(4)
        assert not runtime.keyboard.pressed();assert str(runtime.recorder.directory)==first
        # Target is paused and resumed, while STOP cancels it.
        name=next(iter(runtime.scene.motion.controller.states));state=runtime.scene.motion.controller.states[name]
        target=min(state.maximum,max(state.minimum,state.angle+2.))
        cmd('motion',{'joints':{name:{'mode':'target','target':target,'speed':1.}}})
        cmd('pause');angle=runtime.scene.motion.controller.states[name].angle
        for _ in range(4):await runtime.scene.app.next_update_async()
        assert runtime.scene.motion.controller.states[name].angle==angle
        cmd('play');await steps(5);check_pose()
        assert abs(runtime.scene.motion.controller.states[name].angle-angle)>1e-4
        cmd('keyboard',{'enabled':True});keys(['W']);await steps(2)
        wall=time.monotonic();native=runtime.clock.last
        await steps(180);check_pose()
        report['steady_rate']=(runtime.clock.last-native)/(time.monotonic()-wall)
        assert timing,'Native update delta probe received no samples'
        report['manual_mode_during_play']=runtime.scene.loop_runner.get_manual_mode()
        assert not report['manual_mode_during_play'],'Throttling re-enabled manual stepping on Play'
        report['target_1x_met']=.9<=report['steady_rate']<=1.1
        report['timing_samples']=deepcopy(timing)
        runtime.scene.timeline.stop();runtime.scene.timeline.commit()
        await runtime.scene.app.next_update_async()
        assert runtime.lifecycle=='stopped' and not runtime.failed
        if runtime.drains:await asyncio.gather(*runtime.drains)
        a=Trajectory.load(first);assert a.metadata['end_reason']=='native_stop'
        assert a.metadata['time_base']=='native_simulation_seconds'
        assert a.metadata['recording_complete'] and runtime.recorder is None
        assert a.states[-1]['native_preview_time_s']==a.metadata['last_valid_native_time_s']
        cmd('play');await rebound();await steps(5)
        assert not runtime.keyboard.pressed()
        assert not any(s.running for s in runtime.scene.motion.controller.states.values())
        second=cmd('record_start')['path'];assert second!=first
        await steps(5);keys(['Z','Q','U','I','O']);await steps(5);check_pose()
        cmd('stop');cmd('stop')
        if runtime.drains:await asyncio.gather(*runtime.drains)
        b=Trajectory.load(second);assert b.metadata['end_reason']=='native_stop'
        assert b.states[0]['t_sim_s']==0. and b.metadata['recording_complete']
        report.update(state='passed',first_trajectory=first,second_trajectory=second,
            first_rows=len(a.states),second_rows=len(b.states),first_duration_s=a.duration,
            pause_retained_file=True,native_stop_completed=True,web_stop_completed=True,
            rebind_completed=True,zero_old_inputs=True,witness_steps=witness['steps'],
            physics_steps=runtime.stats['physics_steps'],max_physical_velocity=velocity_max,
            max_position_error_m=position_error_max,max_joint_error_deg=joint_error_max,
            rate=runtime._rate_statistics(),play_every_frame=runtime.scene.timeline.get_play_every_frame(),
            statistics=runtime.stats)
    except Exception:
        report.update(state='failed',error=traceback.format_exc(),runtime_error=runtime.error if runtime else None)
    finally:
        if runtime:
            timing_subscription=None
            if witness_callback is not None:runtime.scene.manager.deregister_callback(witness_callback)
            try:await runtime.close()
            except Exception:report.update(state='failed',close_error=traceback.format_exc())
        write_json(path,report)
        print('S0602_CONTINUOUS_ACCEPTANCE '+json.dumps(report),flush=True)
        omni.kit.app.get_app().post_quit(0 if report['state']=='passed' else 1)

task=asyncio.ensure_future(main())
