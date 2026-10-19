"""Bounded existing-SDK PyTorch profiler check; no package installation."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
INSTALL = Path('/root/isaacsim')
busy = []
for p in Path('/proc').iterdir():
    if not p.name.isdigit():
        continue
    try:
        command = (p/'cmdline').read_bytes()
        if b'/kit/kit' in command or (str(ROOT).encode() in command and b'--worker' in command):
            busy.append(int(p.name))
    except OSError:
        pass
gpu = subprocess.run(['nvidia-smi', '--query-gpu=name,uuid,driver_version', '--format=csv,noheader'],
                     capture_output=True, text=True, timeout=15)
print(json.dumps({'gpu': gpu.stdout.strip(), 'active_project_or_kit_pids': busy,
                  'isaac_python_launcher_exists': (INSTALL/'python.sh').is_file()}))
probe = r'''
import collections, datetime, importlib.util, json, os, pathlib, platform, sys, traceback
archive=pathlib.Path('/root/isaacsim/extsDeprecated/omni.isaac.ml_archive/pip_prebundle')
if (archive/'torch/__init__.py').is_file(): sys.path.insert(0,str(archive))
root=pathlib.Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
out=root/'reports/profiler_probe'/('pytorch_'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+str(os.getpid()))
out.mkdir(parents=True,exist_ok=False)
result={'python':platform.python_version(),'scope':'existing Isaac Sim python.sh plus installed ML archive path, isolated process; no Kit/render session',
        'archive_path':str(archive),
        'output_relative':str(out.relative_to(root)),'torch_spec_found':importlib.util.find_spec('torch') is not None,
        'gpu_test_deferred_due_to_live_kit':os.environ.get('PROFILER_PROBE_GPU_BUSY')=='1'}
try:
    import torch
    from torch.profiler import profile, record_function, ProfilerActivity
    result.update(torch_version=torch.__version__,torch_cuda_build=torch.version.cuda,
                  cuda_available=torch.cuda.is_available(),profiler_module=torch.profiler.__file__,
                  supported_activities=sorted(str(a) for a in torch.profiler.supported_activities()))
    if hasattr(torch.profiler,'kineto_available'):
        result['kineto_available']=torch.profiler.kineto_available()
    cuda=bool(result['cuda_available']) and not result['gpu_test_deferred_due_to_live_kit']
    if cuda: result['gpu_name']=torch.cuda.get_device_name(0)
    cpu=torch.ones((128,128))
    device=torch.randn((256,256),device='cuda') if cuda else None
    if cuda:
        warm=device@device
        torch.cuda.synchronize()
    activities=[ProfilerActivity.CPU]+([ProfilerActivity.CUDA] if cuda else [])
    with profile(activities=activities,record_shapes=False,profile_memory=False,with_stack=False) as prof:
        with record_function('isaac_environment_profiler_probe'):
            for _ in range(3):
                cpu_result=cpu@cpu
                if cuda: gpu_result=device@device
            if cuda: torch.cuda.synchronize()
    trace=out/'trace.json'
    prof.export_chrome_trace(str(trace))
    events=json.loads(trace.read_text())['traceEvents']
    counts=collections.Counter(str(e.get('cat','')) for e in events)
    kernels=[e for e in events if str(e.get('cat','')).lower()=='kernel']
    result.update(profile_context_succeeded=True,trace_bytes=trace.stat().st_size,
                  trace_categories=dict(counts),cpu_operator_events=counts.get('cpu_op',0),
                  user_annotation_events=counts.get('user_annotation',0),
                  cuda_kernel_events=len(kernels),cuda_kernel_names=sorted(set(e['name'] for e in kernels))[:5],
                  cpu_trace_usable=counts.get('cpu_op',0)>0,cuda_trace_usable=bool(kernels) if cuda else None)
except Exception as exc:
    result.update(error=str(exc),traceback=traceback.format_exc())
(out/'result.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
'''
env = os.environ.copy()
for key in ('PYTHONHOME', 'PYTHONPATH', 'LD_LIBRARY_PATH', 'LD_PRELOAD', 'VIRTUAL_ENV', 'CONDA_PREFIX'):
    env.pop(key, None)
env.update(PYTHONDONTWRITEBYTECODE='1', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
           PROFILER_PROBE_GPU_BUSY='1' if busy else '0')
try:
    completed = subprocess.run([str(INSTALL/'python.sh'), '-c', probe], cwd=INSTALL, env=env,
                               capture_output=True, text=True, timeout=60)
    print(json.dumps({'exit_code': completed.returncode, 'stdout': completed.stdout[-12000:],
                      'stderr': completed.stderr[-5000:]}))
except subprocess.TimeoutExpired as exc:
    print(json.dumps({'timeout': True, 'stage': 'isolated interpreter/profiler check'}))
    raise SystemExit(124)
