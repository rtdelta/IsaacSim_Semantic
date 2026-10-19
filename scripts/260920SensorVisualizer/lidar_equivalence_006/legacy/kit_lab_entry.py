"""Isaac entry point for an isolated experiment; formal v06 stays untouched."""
import asyncio,json,os,sys,threading,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT),str(ROOT/'frozen_runtime')]

async def main():
    import omni.kit.app,omni.kit.viewport.utility
    from sensor_visualizer_v06.contracts import load_job
    from sensor_visualizer_v06.replay_capture import ReplayCapture
    from lab.instrumentation import Probe
    from lab.host_pool import HostPool
    from lab.scene_lease import SceneLease
    from sensor_visualizer_v06.diagnostics import RunDiagnostics
    from lab.sdk_copy import ImmediateWriterCopy
    from lab.warm_routing import WarmRouting
    spec=json.loads(Path(os.environ['SL06_SPEC']).read_text())
    sys.path.insert(0,str(ROOT.parent))
    from observations import install_legacy
    install_legacy(Path(os.environ['SL06_SPEC']).parent)
    if spec.get('nc006_raw_probe'):
        from legacy_raw_probe import install
        install(Path(os.environ['SL06_SPEC']).parent)
    Path(os.environ['SL06_PID_FILE']).write_text(str(os.getpid()))
    sdk_copy=ImmediateWriterCopy() if spec.get('rgb_immediate_copy',False) else None
    if sdk_copy:sdk_copy.install()
    routing=WarmRouting() if spec.get('isolated_camera_warmup',False) else None
    if routing:routing.install()
    pool=HostPool() if spec.get('host_pool',False) else None
    if pool:pool.install()
    probe=Probe(spec);probe.install();code=1
    lease=SceneLease() if spec.get('episodes',1)>1 else None
    if lease:lease.install()
    viewport=omni.kit.viewport.utility.get_active_viewport()
    if viewport:viewport.updates_enabled=False
    try:
        sessions=[];job=load_job(os.environ['SV06_JOB'])
        for episode in range(spec.get('episodes',1)):
            capture=ReplayCapture(ROOT/'frozen_runtime',job)
            capture.diag.set_manifest(lab_spec=spec,episode=episode,baseline_copy='frozen_runtime',
                lab_limitations='SDK buffer lifetime and Vulkan-to-CUDA fence unexposed; no unsafe cross-group copy')
            code=await capture.run();sessions.append(str(capture.session))
            Path(os.environ['SL06_SPEC']).parent.joinpath('sessions.json').write_text(json.dumps(sessions))
            if code:break
        if lease:
            diag=RunDiagnostics(job['output_directory'],job['diagnostics'],ROOT/'frozen_runtime',role='cleanup')
            try:await lease.final_close(diag)
            finally:await asyncio.to_thread(diag.close)
    except BaseException:
        code=1
        traceback.print_exc()
    finally:
        if lease:lease.uninstall()
        probe.uninstall()
        if pool:pool.uninstall()
        if sdk_copy:sdk_copy.uninstall()
        if routing:routing.uninstall()
        timer=threading.Timer(20,lambda:os._exit(code));timer.daemon=True;timer.start()
        omni.kit.app.get_app().post_quit(code)
task=asyncio.ensure_future(main())
