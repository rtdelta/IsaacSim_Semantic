"""Native GUI acceptance using OS key events directed only to this Kit's window."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from single0602_headless.interactive_runtime import InteractiveRuntime
from single0602_headless.contracts import write_json


def xdo(*args):
    result=subprocess.run(['/usr/bin/xdotool',*map(str,args)],capture_output=True,text=True,timeout=5)
    if result.returncode:raise RuntimeError(result.stderr)
    return result.stdout.strip()


async def main():
    import omni.kit.app
    import omni.kit.viewport.utility
    import omni.ui as ui
    app=omni.kit.app.get_app();runtime=None;window_id=None;code=1
    report={'state':'starting','input_channel':'X11 xdotool OS events to exact owned Kit window'}
    path=ROOT/'reports/gui_input.json';write_json(path,report)
    try:
        runtime=InteractiveRuntime(ROOT,job_path=ROOT/'config/interactive.json')
        await runtime.initialize(open_scene=True)
        ids=xdo('search','--onlyvisible','--pid',os.getpid()).splitlines()
        windows=[]
        for identity in ids:
            geometry=dict(line.split('=',1) for line in xdo('getwindowgeometry','--shell',identity).splitlines() if '=' in line)
            windows.append((int(geometry.get('WIDTH',0))*int(geometry.get('HEIGHT',0)),identity,geometry))
        _,window_id,geometry=max(windows)
        report['window']={'id':window_id,'geometry':geometry}
        xdo('windowactivate','--sync',window_id)
        xdo('windowfocus','--sync',window_id)
        viewport=omni.kit.viewport.utility.get_active_viewport_window()
        async def focus_viewport():
            viewport.focus()
            await app.next_update_async();await asyncio.sleep(.1)
            context=runtime._native_context()
            if not context['viewport_focused']:
                xdo('mousemove',int(viewport.position_x+viewport.width/2),int(viewport.position_y+viewport.height/2));xdo('click',1)
                await asyncio.sleep(.1)
            assert runtime._native_context()['viewport_focused'],runtime._native_context()
        def key(action):
            assert xdo('getwindowfocus')==window_id,'Refuse key event to a different application'
            xdo(action,'w')
        def position():return runtime._read_state()['position_world_m']
        def distance(a,b):return sum((x-y)**2 for x,y in zip(a,b))**.5
        await focus_viewport()
        runtime.command({'action':'record_start'});runtime.command({'action':'play'})
        runtime.command({'action':'keyboard','payload':{'enabled':True}})
        before=position();key('keydown');await asyncio.sleep(.25);key('keyup');await asyncio.sleep(.05)
        moved=distance(before,position());assert moved>.001,(moved,runtime.native.last_event,runtime.native.focus)
        report['physical_w_translation_m']=moved
        key('keydown');await asyncio.sleep(.1)
        runtime.command({'action':'keyboard','payload':{'enabled':False}})
        frozen=position();await asyncio.sleep(.1)
        runtime.command({'action':'keyboard','payload':{'enabled':True}})
        await asyncio.sleep(.7)
        residual=distance(frozen,position());assert residual<3e-5,residual
        key('keyup');key('keydown');await asyncio.sleep(.15);key('keyup');await asyncio.sleep(.05)
        assert distance(frozen,position())>.001
        report['mode_reenable_while_physically_held_residual_m']=residual
        key('keydown');await asyncio.sleep(.1)
        panel=ui.Window('S0602 Input Focus Test',width=350,height=130)
        with panel.frame:
            with ui.VStack():
                ui.Label('Native motion must stop while editing this field')
                field=ui.StringField()
        panel.focus();await app.next_update_async()
        if hasattr(field,'focus_keyboard'):field.focus_keyboard()
        await asyncio.sleep(.1)
        runtime.native.poll_focus();context=runtime._native_context()
        assert not context['viewport_focused'],context
        frozen=position();await asyncio.sleep(.2);assert distance(frozen,position())<3e-5
        key('keyup');key('keydown');await asyncio.sleep(.15);key('keyup')
        assert distance(frozen,position())<3e-5
        report['text_focus_context']=context
        report['text_field_value']=field.model.get_value_as_string()
        panel.visible=False;await focus_viewport()
        key('keydown');await asyncio.sleep(.15);key('keyup');await asyncio.sleep(.05)
        assert distance(frozen,position())>.001
        runtime.command({'action':'pause'})
        runtime.command({'action':'record_stop','command_id':'gui_end','accepted_ns':time.monotonic_ns()})
        if runtime.drains:await asyncio.gather(*list(runtime.drains))
        report.update(state='passed',trajectory=runtime.last_trajectory,native_events=runtime.native.events,
            last_engine_key_to_pose_ms=runtime.keyboard.last_apply_ms,statistics=runtime.stats)
        code=0
    except Exception:
        report.update(state='failed',error=traceback.format_exc());traceback.print_exc()
    finally:
        if window_id:
            try:xdo('keyup','--window',window_id,'w')
            except Exception:pass
        if runtime:
            try:await runtime.close()
            except Exception:report['close_error']=traceback.format_exc()
        write_json(path,report)
        print('S0602_GUI '+json.dumps(report),flush=True)
        app.post_quit(code)

task=asyncio.ensure_future(main())
