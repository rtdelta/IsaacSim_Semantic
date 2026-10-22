"""Read-only capability query: no application profiling, install or project import."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

def run(args, selected=None):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=12)
        out = r.stdout
        if selected:
            lines = out.splitlines()
            out = '\n'.join(line for line in lines if any(k in line.lower() for k in selected))
        return {'exit_code': r.returncode, 'stdout': out[:13000], 'stderr': r.stderr[:2500]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'error': type(exc).__name__ + ': ' + str(exc)}

nsys = '/opt/nvidia/nsight-compute/2025.1.1/host/target-linux-x64/nsys'
base = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06')
out = {'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
       'intent': 'read only: static capability/help queries; no workload launched', 'sources': []}
for rel in ('sensor_visualizer_v06/sensors.py', 'sensor_visualizer_v06/scene.py',
            'sensor_visualizer_v06/contracts.py', 'sensor_visualizer_v06/pipeline.py',
            'tools/start_native_trace.py'):
    p = base / rel
    out['sources'].append({'relative_path': rel, 'exists': p.is_file(),
                           'sha256': hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None})
if Path(nsys).is_file():
    out['nsys_status'] = run([nsys, 'status', '--environment'])
    out['gpu_metrics_devices_help'] = run([nsys, 'profile', '--gpu-metrics-devices=help'])
    out['gpu_metrics_set_help'] = run([nsys, 'profile', '--gpu-metrics-devices=0', '--gpu-metrics-set=help'])
    out['profile_help_features'] = run([nsys, 'profile', '--help'],
        ('gpu-metrics', 'gpu-context', 'cpuctxsw', 'cuda-memory', 'vulkan-gpu', 'capture-range', 'cuda-event', 'backtrace'))
out['gpu'] = run(['nvidia-smi', '--query-gpu=index,name,driver_version,utilization.gpu,memory.used,pcie.link.gen.current', '--format=csv,noheader,nounits'])
print(json.dumps(out, indent=2))
