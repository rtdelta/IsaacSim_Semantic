"""Bounded native PhysX validation and preview capture, with no saved motion edits."""
import asyncio
import json
import math
from pathlib import Path
import traceback
import numpy as np
import omni.kit.app
import omni.usd
import omni.timeline
import omni.physx
from pxr import Gf, Usd, UsdGeom, UsdPhysics

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('Hinge_Slew', 'Hinge_Boom', 'Hinge_Arm', 'Hinge_Bucket')


def progress(phase):
    (ROOT/'reports/validation_progress.json').write_text(json.dumps({'phase':phase}))
    print('CET200_QA',phase,flush=True)


async def main():
    app=omni.kit.app.get_app()
    timeline=omni.timeline.get_timeline_interface()
    report={'passed':False}
    try:
        progress('open_payload_preview')
        ctx=omni.usd.get_context()
        await ctx.open_stage_async(str(ROOT/'usd/CET200_preview.usda'))
        stage=ctx.get_stage()
        stage.SetEditTarget(stage.GetSessionLayer())
        allj=[p for p in stage.Traverse() if p.IsA(UsdPhysics.RevoluteJoint)]
        main={n:next(p for p in allj if p.GetName()==n) for n in NAMES}
        report['articulation_roots']=[str(p.GetPath()) for p in stage.Traverse() if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
        assert report['articulation_roots']
        async def frames(n):
            for _ in range(n): await app.next_update_async()
        await frames(12)
        try:
            from omni.kit.viewport.utility import get_active_viewport, capture_viewport_to_file
            viewport=get_active_viewport()
            viewport.camera_path='/World/Camera'
            viewport.set_texture_resolution((1280,720))
            await frames(30)
            capture=capture_viewport_to_file(viewport,str(ROOT/'reports/CET200_preview.png'))
            await capture.wait_for_result()
            report['screenshot']='reports/CET200_preview.png'
        except Exception:
            report['screenshot_error']=traceback.format_exc()
        def snapshot():
            omni.physx.get_physx_interface().update_transformations(False,True,False,False)
            cache=UsdGeom.XformCache(Usd.TimeCode.Default())
            out={}
            for name,prim in main.items():
                j=UsdPhysics.RevoluteJoint(prim)
                matrices=[]
                for idx in (0,1):
                    rel=getattr(j,'GetBody'+str(idx)+'Rel')().GetTargets()
                    body=cache.GetLocalToWorldTransform(stage.GetPrimAtPath(rel[0]))
                    q=getattr(j,'GetLocalRot'+str(idx)+'Attr')().Get()
                    p=getattr(j,'GetLocalPos'+str(idx)+'Attr')().Get()
                    local=Gf.Matrix4d().SetRotate(Gf.Quatd(q))
                    local.SetTranslateOnly(Gf.Vec3d(p))
                    matrices.append(np.array(local*body).T)
                a,b=matrices
                R=a[:3,:3].T@b[:3,:3]
                axis=j.GetAxisAttr().Get()
                angle={'X':lambda:math.atan2(R[2,1],R[1,1]),
                       'Y':lambda:math.atan2(R[0,2],R[0,0]),
                       'Z':lambda:math.atan2(R[1,0],R[0,0])}[axis]()
                out[name]={'angle_deg':math.degrees(angle),
                           'anchor_error_m':float(np.linalg.norm(a[:3,3]-b[:3,3]))}
            return out
        progress('simulate_zero_pose')
        timeline.play()
        await frames(100)
        report['initial']=snapshot()
        for row in report['initial'].values():
            assert abs(row['angle_deg'])<.1,report['initial']
            assert row['anchor_error_m']<.002,report['initial']
        report['motion_cases']=[]
        for case in ([10,8,-12,15],[-10,-8,12,-15]):
            progress('drive_'+str(case))
            for name,target in zip(NAMES,case):
                UsdPhysics.DriveAPI(main[name],'angular').GetTargetPositionAttr().Set(float(target))
            await frames(180)
            actual=snapshot()
            row={'targets_deg':dict(zip(NAMES,case)),'actual':actual}
            report['motion_cases'].append(row)
            for name,target in zip(NAMES,case):
                assert abs(actual[name]['angle_deg']-target)<.3,row
                assert actual[name]['anchor_error_m']<.002,row
        timeline.stop()
        await frames(5)
        report['passed']=True
        progress('passed')
    except Exception:
        report['error']=traceback.format_exc()
        print(report['error'],flush=True)
        timeline.stop()
        progress('failed')
    (ROOT/'reports/validation_report.json').write_text(json.dumps(report,indent=2))
    app.post_quit(0 if report['passed'] else 1)


asyncio.ensure_future(main())
