"""Fixed pose quality comparison in an isolated headless process."""
import asyncio
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
    import carb.settings
    import omni.kit.app
    import numpy as np
    from PIL import Image
    from pxr import UsdRender
    from sensor_visualizer_v02.contracts import load_job,write_json,assert_frozen
    from sensor_visualizer_v02.scene import SceneStepper
    job=load_job(overrides={'sensors':{'camera_ids':['front'],'lidar_ids':['MyAiry_front']}})
    output=ROOT/'reports/quality'; output.mkdir(parents=True,exist_ok=True)
    scene=SceneStepper(ROOT,job); result={'state':'running','samples':[]}; code=1
    try:
        await scene.initialize()
        result['assets']=scene.asset_manifest
        result['channels_prims']=[{'path':str(p.GetPath()),'type':p.GetTypeName(),
            'channels':str(p.GetAttribute('channels').Get())} for p in scene.stage.Traverse() if p.GetAttribute('channels')]
        result['gaussian_prims']=[{'path':str(p.GetPath()),'type':p.GetTypeName()} for p in scene.stage.Traverse()
            if any(word in (p.GetTypeName()+' '+str(p.GetPath())).lower() for word in ('gaussian','splat','3dgs'))][:60]
        for mode,subframes in [(0,2),(2,2),(2,8),(2,16)]:
            settings=carb.settings.get_settings(); settings.set('/rtx/post/dlss/execMode',mode)
            for prim in scene.stage.Traverse():
                if prim.IsA(UsdRender.Settings):
                    attr=prim.GetAttribute('omni:rtx:post:dlss:execMode')
                    if attr: attr.Set(('performance','balanced','quality','auto')[mode])
            before=scene.native_time(); started=time.perf_counter()
            await scene.drivers.render(subframes); assert_frozen(before,scene.native_time())
            # This diagnostic changes image renderer settings at fixed time.
            # It measures camera convergence only, not LiDAR scan scheduling.
            arrays,cameras,_=scene.drivers.read(round(before*1e9),kinds=('cameras',))
            image=arrays['camera/front'][:,:,:3].copy()
            name=f'dlss{mode}_subframes{subframes}.png'; Image.fromarray(image).save(output/name,compress_level=1)
            gray=image.astype(float).mean(axis=2)
            gradients=np.abs(np.diff(gray,axis=0)).mean()+np.abs(np.diff(gray,axis=1)).mean()
            result['samples'].append({'file':name,'dlss_mode':settings.get('/rtx/post/dlss/execMode'),'subframes':subframes,
              'source_time_s':before,'wall_s':time.perf_counter()-started,'mean_abs_gradient':float(gradients),'camera':cameras['front']})
        result['state']='finished'; code=0
    except Exception: result.update(state='failed',error=traceback.format_exc()); traceback.print_exc()
    finally:
        try: await scene.close()
        except Exception as exc: result['cleanup_error']=str(exc)
        write_json(output/'report.json',result)
        timer=threading.Timer(15,lambda:os._exit(code)); timer.daemon=True; timer.start()
        omni.kit.app.get_app().post_quit(code)

_task=asyncio.ensure_future(main())
