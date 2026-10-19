"""Private finite validation driver, intentionally outside the shareable package."""
import argparse, hashlib, json, os, shutil, subprocess, time
from pathlib import Path

ROOT = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')


def competitors():
    found = []
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            if b'/kit/kit' in (p / 'cmdline').read_bytes():
                found.append(int(p.name))
        except OSError:
            pass
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--id', required=True)
    args = parser.parse_args()
    if not args.id.replace('_', '').isalnum():
        raise ValueError('Invalid suite ID')
    out = ROOT / 'reports/issue_repro' / args.id
    if not args.worker:
        if competitors() or shutil.disk_usage(ROOT).free < 2*1024**3:
            raise RuntimeError('Competing Kit or insufficient disk space')
        out.mkdir(parents=True, exist_ok=False)
        with (out/'worker.log').open('xb') as log:
            child = subprocess.Popen(['/usr/bin/python3', '-B', str(Path(__file__).resolve()),
                                      '--id', args.id, '--worker'], cwd=ROOT, stdout=log,
                                     stderr=subprocess.STDOUT, start_new_session=True)
        print(json.dumps({'worker_pid': child.pid, 'directory': str(out)}))
        return
    status = {'state': 'running', 'runs': [], 'suite': args.id}
    def save():
        (out/'status.json').write_text(json.dumps(status, indent=2))
    try:
        for name, rate, motion in [('static_on', 0, 'on'), ('rotate_on', 6, 'on'),
                                   ('static_off', 0, 'off'), ('rotate_off', 6, 'off')]:
            if competitors():
                raise RuntimeError('Competing Kit before ' + name)
            status['active'] = name
            save()
            command = ['/usr/bin/python3', '-B', str(ROOT/'repro/instant_lidar_timing/launch.py'),
                       '--isaac-root', '/root/isaacsim', '--out', str(out/name),
                       '--yaw-rate', str(rate), '--motion-bvh', motion, '--targets', '20']
            env = os.environ.copy()
            for key in ('PYTHONHOME', 'PYTHONPATH', 'LD_LIBRARY_PATH', 'LD_PRELOAD', 'VIRTUAL_ENV', 'CONDA_PREFIX'):
                env.pop(key, None)
            env.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
            with (out/(name+'.log')).open('xb') as log:
                result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            summary_path = out/name/'summary.json'
            summary = json.loads(summary_path.read_text()) if summary_path.exists() else None
            status['runs'].append({'name': name, 'exit_code': result.returncode, 'summary': summary})
            save()
            if result.returncode != 0 or not summary or not summary.get('measurement_qualified'):
                raise RuntimeError('Stop for inspection: ' + name)
        status['state'] = 'complete'
        status['remaining_kit_pids'] = competitors()
    except Exception as exc:
        status.update(state='stopped_for_inspection', error=str(exc))
    save()


if __name__ == '__main__':
    main()
