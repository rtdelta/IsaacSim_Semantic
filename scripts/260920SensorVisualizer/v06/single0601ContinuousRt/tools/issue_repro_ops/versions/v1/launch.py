"""Run one isolated reproduction using an existing Linux Isaac Sim installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--isaac-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='New output directory')
    parser.add_argument('--yaw-rate', type=float, choices=(0., 3., 6.), default=6.)
    parser.add_argument('--motion-bvh', choices=('on', 'off'), default='on')
    parser.add_argument('--targets', type=int, default=20)
    parser.add_argument('--gui', action='store_true', help='Requires an existing DISPLAY')
    args = parser.parse_args()
    if not 4 <= args.targets <= 100:
        parser.error('--targets must be between 4 and 100')
    install, here, out = args.isaac_root.resolve(), Path(__file__).resolve().parent, args.out.resolve()
    if not (install / 'kit/kit').is_file():
        parser.error('Expected Linux binary <isaac-root>/kit/kit')
    out.mkdir(parents=True, exist_ok=False)
    spec = {'yaw_rate_deg_s': args.yaw_rate, 'motion_bvh': args.motion_bvh == 'on',
            'targets': args.targets, 'physics_hz': 60, 'scan_hz': 10, 'gui': args.gui,
            'isaac_root': str(install), 'output': str(out), 'timeout_s': 600}
    (out / 'request.json').write_text(json.dumps(spec, indent=2))
    sources = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(here.iterdir()) if p.suffix in ('.py', '.json')}
    (out / 'source_hashes.json').write_text(json.dumps(sources, indent=2))
    env = os.environ.copy()
    for key in ('PYTHONHOME', 'PYTHONPATH', 'LD_PRELOAD', 'VIRTUAL_ENV', 'CONDA_PREFIX'):
        env.pop(key, None)
    libraries = [str(p) for pattern in ('omni.sensors.nv.common-*/bin/checker_lib/bin',
                 'omni.sensors.nv.common-*/bin', 'omni.sensors.nv.lidar-*/bin/model_plugins')
                 for p in (install / 'extscache').glob(pattern)]
    libraries += [str(install / p) for p in ('kit/python/lib', 'kit', 'kit/kernel/plugins', 'kit/plugins/rtx')]
    env.update(LD_LIBRARY_PATH=':'.join(libraries), PYTHONUNBUFFERED='1',
               LIDAR_REPRO_REQUEST=str(out / 'request.json'))
    command = [str(install / 'kit/kit'), str(install / 'apps/isaacsim.exp.full.kit'), '--allow-root',
               '--/renderer/multiGpu/enabled=false', '--/persistent/app/newStage/defaultTemplate=empty',
               '--/app/settings/persistent=false', '--/app/extensions/registryEnabled=false',
               '--/app/extensions/syncRegistryOnStartup=false', '--/app/asyncRendering=false',
               '--/exts/isaacsim.core.throttling/enable_async=false', '--/app/renderer/skipWhileMinimized=false',
               '--/rtx/hydra/supportMultiTickRate=true', '--/rtx/rendering/perSensorTickTlas=true',
               '--/renderer/raytracingMotion/enabled=' + str(spec['motion_bvh']).lower(),
               '--/rtx/scenedb/maxHistoryTransformCount=64', '--/crashreporter/enabled=false',
               '--/crashreporter/skipOldDumpUpload=true', '--/crashreporter/url=',
               '--/telemetry/enableAnonymousData=false',
               '--/exts/omni.services.transport.server.http/http/enabled=false',
               '--enable', 'isaacsim.sensors.rtx.nodes', '--enable', 'isaacsim.core.rendering_manager',
               '--exec', str(here / 'capture.py')]
    if not args.gui:
        command += ['--no-window', '--/app/window/enabled=false']
    (out / 'launch.json').write_text(json.dumps({'argv': command}, indent=2))
    with (out / 'kit.log').open('xb') as log:
        child = subprocess.Popen(command, cwd=install, env=env, stdout=log,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        (out / 'process.json').write_text(json.dumps({'pid': child.pid}))
        timed_out = False
        try:
            code = child.wait(timeout=spec['timeout_s'])
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            code = 124
    (out / 'process.json').write_text(json.dumps({'pid': child.pid, 'exit_code': code,
                                                 'timed_out': timed_out, 'exited': True}, indent=2))
    if (out / 'summary.json').exists():
        print((out / 'summary.json').read_text())
    else:
        print('No summary produced; inspect ' + str(out / 'kit.log'))
    return code


if __name__ == '__main__':
    sys.exit(main())
