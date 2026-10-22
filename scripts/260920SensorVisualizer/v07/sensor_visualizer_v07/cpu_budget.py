"""Project process limits, preserving the platform's cgroup and system settings."""
import os
from pathlib import Path

def read_budget(root='/sys/fs/cgroup'):
    root = Path(root)
    quota = None
    try:
        maximum, period = (root/'cpu.max').read_text().split()
        quota = None if maximum == 'max' else int(maximum)/int(period)
    except (OSError, ValueError):
        pass
    affinity = sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else list(range(os.cpu_count() or 1))
    return {'visible_logical_cpus': os.cpu_count(), 'inherited_affinity': affinity,
            'quota_cpu_equivalents': quota, 'cgroup_path': str(root),
            'meaning': 'CFS time budget, not exclusive physical cores'}

def launch_budget(role, options):
    budget = read_budget()
    key = 'interactive_threads' if role == 'interactive' else 'capture_threads'
    count = min(int(options[key]), max(1, int(budget['quota_cpu_equivalents'] or len(budget['inherited_affinity']))))
    explicit = options.get(role+'_affinity')
    if explicit:
        chosen = sorted(set(map(int, explicit)))
        if not set(chosen) <= set(budget['inherited_affinity']):
            raise ValueError('CPU affinity must be contained in the inherited cpuset')
        os.sched_setaffinity(0, chosen)
    budget.update(role=role, work_pool_limit=count, effective_affinity=sorted(os.sched_getaffinity(0)))
    flags = [f'--/plugins/carb.tasking.plugin/threadCount={count}',
             f'--/plugins/omni.tbb.globalcontrol/maxThreadCount={count}',
             '--/persistent/physics/numThreads='+str(min(count, int(options['physics_threads'])))]
    env = {name:'1' for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')}
    return flags, env, budget
