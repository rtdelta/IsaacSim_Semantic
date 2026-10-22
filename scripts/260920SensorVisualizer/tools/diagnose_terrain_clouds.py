import asyncio
import json
from pathlib import Path
import sys
import traceback
import omni.kit.app
import omni.usd
import omni.graph.core as og
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
OUT=ROOT/'reports/tilt_terrain/cloud_diagnostic.json'


async def main():
    app=omni.kit.app.get_app();manager=None;result={}
    def stats(r):
        data={sid:dict(vars(s)) for sid,s in r.cloud_publishers.stats.items()}
        data['ros_nodes']=[{n:a.get() for n in ['inputs:context','inputs:bufferSize','inputs:timeStamp']
                           if (a:=node.get_attribute(n)).is_valid()}
            for g in og.get_all_graphs() for node in g.get_nodes()
            if node.get_type_name()=='isaacsim.ros2.bridge.ROS2PublishPointCloud']
        return data
    try:
        from sensor_visualizer.config import load_config
        from sensor_visualizer.session import SceneSession
        cfg=load_config(ROOT/'config/sensors.json');cfg['ros_domain_id']=141
        cfg['output_directory']=str(ROOT/'reports/tilt_terrain/diagnostic_recordings')
        for name in ['combine_scene_16_terrain_fisheye.usda','combine_scene_15_surround_fisheye.usda']:
            assert (await omni.usd.get_context().open_stage_async('/root/gpufree-data/IsaacSim_Asset/combine_stage/'+name))[0]
            manager=SceneSession(ROOT,config=cfg,artifact_dir=ROOT/'reports/tilt_terrain/cloud_diagnostic',show_ui=False)
            await manager.refresh();r=manager.instance;assert r,manager.error
            r.timeline.play()
            for _ in range(30):await app.next_update_async()
            result[name]={'initial':stats(r)};OUT.write_text(json.dumps(result,indent=2))
            r.timeline.pause()
            for _ in range(4):await app.next_update_async()
            r.motion.command_base('height',z=r.motion.base_controller.z+.35)
            r.motion.command_tilt('execute',commands={'pitch':{'mode':'direct','target':10}})
            r.timeline.play()
            for _ in range(30):await app.next_update_async()
            result[name]['resumed']=stats(r);OUT.write_text(json.dumps(result,indent=2))
            await manager.close();manager=None
    except Exception:result['error']=traceback.format_exc();print(result['error'],flush=True)
    finally:
        if manager:await manager.close()
        await omni.usd.get_context().close_stage_async()
        OUT.write_text(json.dumps(result,indent=2));app.post_quit(1 if 'error' in result else 0)


_task=asyncio.ensure_future(main())
