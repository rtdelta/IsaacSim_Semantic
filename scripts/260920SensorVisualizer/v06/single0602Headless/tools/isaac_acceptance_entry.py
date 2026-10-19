"""Native Isaac acceptance; injected input is reported separately from physical UI input."""
import asyncio
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback
from types import SimpleNamespace as NS

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from single0602_headless.interactive_runtime import InteractiveRuntime
from single0602_headless.contracts import write_json
from single0602_headless.trajectory import Trajectory


async def main():
    import omni.kit.app
    report={'state':'running','native_viewport_physical_input':'not tested',
            'coordinate_position_tolerance_m':3e-5,'angle_tolerance_deg':1e-3,'mode_toggles':0}
    report_path=ROOT/'reports/isaac_acceptance.json'
    write_json(report_path,report)
    runtime=None
    code=1
    try:
        runtime=InteractiveRuntime(ROOT,job_path=ROOT/'config/interactive.json')
        await runtime.initialize(open_scene=True)
        report['startup']=runtime.scene.motion.frame_metadata()
        assert not runtime.keyboard.enabled
        runtime.command({'action':'record_start'})
        start=runtime.time_s
        runtime.command({'action':'play'})
        native_sequence=0
        for index in range(20):
            before=runtime._read_state()
            runtime.command({'action':'keyboard','payload':{'enabled':True}})
            after=runtime._read_state()
            assert max(abs(a-b) for a,b in zip(before['position_world_m'],after['position_world_m']))<3e-5
            native_sequence+=1
            runtime.command({'action':'keys','payload':{'source':'web:acceptance','keys':['W'],
                'input_epoch':runtime.keyboard.input_epoch,'sequence':native_sequence}})
            await asyncio.sleep(.03)
            old=runtime.keyboard.input_epoch
            runtime.command({'action':'keyboard','payload':{'enabled':False}})
            assert runtime.keyboard.pressed()==set()
            try:
                runtime.command({'action':'keys','payload':{'source':'web:acceptance','keys':['W'],
                    'input_epoch':old,'sequence':native_sequence+1}})
            except ValueError:pass
            else:raise AssertionError('Old epoch accepted')
            report['mode_toggles']+=1
        coordinate=[]
        for heading in (0,90,180,-90):
            runtime.command({'action':'pause'})
            runtime.command({'action':'motion','payload':{'base':{'yaw_deg':heading},
                'tilt':{'pitch':{'mode':'direct','target':20},'roll':{'mode':'direct','target':-15}}}})
            runtime.command({'action':'keyboard','payload':{'enabled':True}})
            before=runtime._read_state()
            native_sequence+=1
            runtime.command({'action':'play'})
            runtime.command({'action':'keys','payload':{'source':'web:acceptance','keys':['W','A'],
                'input_epoch':runtime.keyboard.input_epoch,'sequence':native_sequence}})
            until=runtime.time_s+.015
            while runtime.time_s<until:await asyncio.sleep(.01)
            runtime.command({'action':'pause'})
            after=runtime._read_state()
            dt=after['t_sim_s']-before['t_sim_s'];a=math.radians(heading+45)
            delta=[b-a0 for a0,b in zip(before['position_world_m'],after['position_world_m'])]
            expected=[.5*dt*math.cos(a),.5*dt*math.sin(a),0.]
            error=max(abs(x-y) for x,y in zip(delta,expected))
            assert error<3e-5,(heading,error,delta,expected)
            coordinate.append({'heading_deg':heading,'dt_s':dt,'delta_m':delta,'max_error_m':error})
        report['coordinate_checks']=coordinate
        runtime.command({'action':'keyboard','payload':{'enabled':False}})
        runtime.command({'action':'play'})
        held=runtime._read_state()
        while runtime.time_s-start<.45:await asyncio.sleep(.02)
        after=runtime._read_state()
        assert max(abs(a-b) for a,b in zip(held['position_world_m'],after['position_world_m']))<3e-5
        runtime.command({'action':'pause'})
        runtime.command({'action':'record_stop','command_id':'acceptance_end','accepted_ns':time.monotonic_ns()})
        if runtime.drains:await asyncio.gather(*list(runtime.drains))
        trajectory=Trajectory.load(runtime.last_trajectory)
        assert trajectory.metadata['recording_complete']
        report.update(trajectory=runtime.last_trajectory,duration_s=trajectory.duration,rows=len(trajectory.states),
            session_id=runtime.session_id,control_events=trajectory.metadata['control_events'],state='passed')
        await runtime.close()
        report['interactive_socket_closed']=not runtime.endpoint.path.exists()
        code=0
    except Exception:
        report.update(state='failed',error=traceback.format_exc())
        traceback.print_exc()
    finally:
        if runtime and not runtime.closed:
            try:await runtime.close()
            except Exception:report['close_error']=traceback.format_exc()
        write_json(report_path,report)
        print('S0602_ACCEPTANCE '+json.dumps(report),flush=True)
        omni.kit.app.get_app().post_quit(code)

task=asyncio.ensure_future(main())
