"""Read-only monitoring inventory; no project import or profiler activation."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

def command(args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=8)
        return {'exit_code': p.returncode, 'stdout': p.stdout[:12000], 'stderr': p.stderr[:1500]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'error': type(exc).__name__ + ': ' + str(exc)}

out = {'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
       'intent': 'read only; no install, benchmark, project import or profiler activation',
       'tools': {n: shutil.which(n) for n in ('nvidia-smi', 'dcgmi', 'nv-hostengine', 'dcgm-exporter', 'nsys', 'ncu', 'pidstat', 'iostat', 'perf')},
       'commands': {}, 'projects': {}, 'pcie': []}
out['commands']['gpu'] = command(['nvidia-smi', '--query-gpu=index,name,uuid,pci.bus_id,driver_version,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,temperature.gpu,pcie.link.gen.max,pcie.link.gen.current,pcie.link.width.max,pcie.link.width.current', '--format=csv,noheader,nounits'])
out['commands']['gpu_processes'] = command(['nvidia-smi', '--query-compute-apps=pid,gpu_uuid,used_gpu_memory', '--format=csv,noheader,nounits'])
out['commands']['pcie_rates'] = command(['nvidia-smi', 'dmon', '-s', 't', '-c', '1'])
out['commands']['topology'] = command(['nvidia-smi', 'topo', '-m'])
for name in ('ncu', 'nsys', 'dcgmi'):
    if out['tools'][name]: out['commands'][name + '_version'] = command([out['tools'][name], '--version'])
params = Path('/proc/driver/nvidia/params')
if params.exists(): out['counter_permission'] = [s for s in params.read_text().splitlines() if 'ProfilingAdminOnly' in s]
for s in ('/opt/nvidia/nsight-systems', '/opt/nvidia/nsight-compute', '/opt/nvidia/nsight-graphics', '/usr/local/cuda/extras/CUPTI', '/usr/lib/x86_64-linux-gnu/libdcgm.so'):
    out.setdefault('known_tool_paths', {})[s] = Path(s).exists()
base = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
for version in ('v05', 'v06', 'v06performance', 'v07'):
    p = base / version
    record = {'exists': p.is_dir(), 'logging_sources': []}
    if p.is_dir():
        for f in sorted(p.glob('sensor_visualizer_*/resource*.py')):
            record['logging_sources'].append({'path': str(f.relative_to(base)), 'sha256': hashlib.sha256(f.read_bytes()).hexdigest()})
    out['projects'][version] = record
inventory = command(['nvidia-smi', '--query-gpu=pci.bus_id', '--format=csv,noheader'])
for raw in inventory.get('stdout', '').splitlines():
    bits = raw.strip().lower().split(':')
    if len(bits) != 3: continue
    address = bits[0][-4:] + ':' + ':'.join(bits[1:])
    p = Path('/sys/bus/pci/devices') / address
    row = {'address': address}
    for name in ('current_link_speed', 'current_link_width', 'max_link_speed', 'max_link_width', 'numa_node'):
        try: row[name] = (p / name).read_text().strip()
        except OSError: pass
    out['pcie'].append(row)
print(json.dumps(out, indent=2))
