"""Exercise real omni.ui controls and pause/stop lifecycle without using the user's GUI."""
import asyncio
import json
import faulthandler
import os
from pathlib import Path
import sys
import threading
import traceback
import time
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
faulthandler.enable(all_threads=False)

async def main():
    import omni.kit.app
    import omni.usd
    from sensor_visualizer_v02.contracts import DEFAULT,write_json
    from sensor_visualizer_v02.ui import CapturePanel
    panel=None; result={'state':'running'}; code=1
    try:
        await omni.usd.get_context().open_stage_async(DEFAULT['scene'])
        panel=CapturePanel(ROOT)
        panel.camera_ids.set_value('front'); panel.lidar_ids.set_value('MyAiry_front')
        panel.preview.set_value(True); panel.groups.set_value(20)
        await panel.initialize()
        assert len(panel.rows)==5
        initial=panel.scene.poses.snapshot()
        panel.mount_xyz[0].set_value(initial[0]['position_m'][0]+.02)
        panel.apply_mount(); panel.save_poses()
        name=next(n for k,n in panel.rows if k=='joints')
        panel.rows[('joints',name)]['target'].set_value(panel.scene.motion.controller.states[name].angle+.5)
        panel.apply_motion('joints',name)
        panel.scene.apply_commands({'tilt':{'roll':{'mode':'periodic','lower':-1,'upper':1,'speed':2}}})
        panel.job_path.set_value(str(ROOT/'reports/ui_saved_job.json')); panel.save_job()
        saved=json.loads((ROOT/'reports/ui_saved_job.json').read_text())
        assert saved['motion']['tilt']['roll']['mode']=='periodic'
        capture=asyncio.ensure_future(panel.capture()); deadline=time.monotonic()+180
        while not panel.runner or panel.runner.groups<1:
            if capture.done(): await capture; raise RuntimeError('Capture ended before first group')
            if time.monotonic()>deadline: raise TimeoutError('UI capture startup')
            await asyncio.sleep(.05)
        panel.pause()
        while panel.runner.phase!='paused':
            if capture.done(): await capture; raise RuntimeError('No pause boundary')
            await asyncio.sleep(.05)
        before=panel.scene.native_time(); await asyncio.sleep(.4)
        if panel.scene.native_time()!=before: raise RuntimeError('Time advanced while UI paused')
        paused_groups=panel.runner.groups
        panel.resume()
        while panel.runner.groups<paused_groups+2 and not capture.done(): await asyncio.sleep(.05)
        panel.stop(); await capture
        if panel.runner.error: raise RuntimeError(panel.runner.error)
        if panel.scene.poses.snapshot()!=initial: raise RuntimeError('Mounts not restored on Stop')
        result.update(state='finished',groups=panel.runner.groups,session=str(panel.runner.session),
                      checks=['UI construction','direct joint control','mount apply/save/reset','job save','pause frozen','resume','stop/drain','ROS preview enabled'])
        code=0
    except Exception: result.update(state='failed',error=traceback.format_exc()); traceback.print_exc()
    finally:
        if panel:
            try: await panel.close()
            except Exception as exc: result['cleanup_error']=str(exc)
        write_json(ROOT/'reports/ui_test.json',result)
        timer=threading.Timer(15,lambda:os._exit(code)); timer.daemon=True; timer.start()
        omni.kit.app.get_app().post_quit(code)

_task=asyncio.ensure_future(main())
