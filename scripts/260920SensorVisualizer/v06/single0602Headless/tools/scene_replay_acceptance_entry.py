"""Record native source trajectories in disposable scenes; never edit source assets."""
import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
import sys
import time
import traceback
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from single0602_headless.contracts import DEFAULT,write_json

async def main():
    import omni.kit.app
    from single0602_headless.interactive_runtime import InteractiveRuntime
    tag=os.environ.get('S0602_TEST_TAG','scene_replay_native')
    output=Path(DEFAULT['output_directory'])/'validation'/tag
    output.mkdir(parents=True,exist_ok=True)
    report={'state':'running','output':str(output)};owner=None
    def save():write_json(ROOT/'reports'/(tag+'.json'),report)
    def command(action,payload=None):
        return owner.command({'action':action,'payload':payload or {},'command_id':str(uuid.uuid4())})
    save()
    try:
        async def record(scene,label):
            nonlocal owner
            job=output/(label+'_job.json')
            write_json(job,{'scene':str(scene),'mode':'interactive','output_directory':str(output/label)})
            owner=InteractiveRuntime(ROOT,output=output/label,job_path=job,
                                     socket_path=Path('/tmp')/('s06sr_'+uuid.uuid4().hex+'.sock'))
            await owner.initialize(open_scene=True)
            result=command('record_start')
            command('motion',{'base':{'speed_m_s':.15,'yaw_rate_deg_s':2}})
            command('play');deadline=time.monotonic()+15
            while owner.time_s<.3:
                if owner.failed:raise RuntimeError(owner.error)
                if time.monotonic()>deadline:raise TimeoutError('Native trajectory did not advance')
                await owner.scene.app.next_update_async()
            command('pause');command('record_stop')
            while owner.drains:await owner.scene.app.next_update_async()
            if owner.trajectory_error:raise RuntimeError(owner.trajectory_error)
            metadata=json.loads((Path(result['path'])/'metadata.json').read_text())
            assert metadata['recording_complete'] and metadata['scene_interface']
            await owner.close();owner=None
            return result['path'],metadata
        base=Path(DEFAULT['scene'])
        assert hashlib.sha256(base.read_bytes()).hexdigest()=='e44ff38c21caaaccf20aa44a9b834e33d7109407e737df27198a63ad95e9fb79'
        source,metadata=await record(base,'baseline')
        baseline={'asset_sha256':metadata['asset_manifest']['asset_profile']['asset_sha256'],
                  'used_layers':metadata['asset_manifest']['used_layers'],'interface':metadata['scene_interface']}
        write_json(output/'verified_legacy_interface.json',{metadata['asset_manifest']['root_sha256']:baseline})
        wrapper=output/'editable.usda'
        # Retain Kit root-layer renderer metadata as well as Stage metadata.
        text=re.sub(r'@([^@]+)@',lambda m:'@'+str((base.parent/m.group(1)).resolve())+'@'
                    if not m.group(1).startswith('/') else m.group(0),base.read_text())
        wrapper.write_text(text,encoding='utf-8')
        trajectory,_=await record(wrapper,'editable_source')
        report.update(state='passed',baseline_trajectory=source,trajectory=trajectory,editable_scene=str(wrapper),
                      legacy_baseline=str(output/'verified_legacy_interface.json'))
    except Exception:report.update(state='failed',error=traceback.format_exc())
    finally:
        if owner:
            try:await owner.close()
            except Exception:report['cleanup_error']=traceback.format_exc()
        save();print('SCENE_REPLAY_ACCEPTANCE='+json.dumps(report),flush=True)
        omni.kit.app.get_app().post_quit(0 if report['state']=='passed' else 1)

task=asyncio.ensure_future(main())
