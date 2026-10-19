"""Read installed callback APIs and task-owned processes without importing Isaac."""
import json
from pathlib import Path

root = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
processes = []
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():
        continue
    try:
        args = (proc/'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
        if str(root) in args and ('kit/kit' in args or 'run_web.py' in args or 'run_capture.py' in args):
            processes.append({'pid': int(proc.name), 'command': args[:1500], 'cwd': str((proc/'cwd').resolve())})
    except (OSError, ProcessLookupError):
        pass
print(json.dumps({'task_processes': processes, 'root_exists': root.is_dir()}))
paths = [
    Path('/root/isaacsim/exts/isaacsim.core.simulation_manager/isaacsim/core/simulation_manager/impl/simulation_manager.py'),
    Path('/root/isaacsim/exts/isaacsim.core.simulation_manager/isaacsim/core/simulation_manager/impl/events.py'),
]
for path in paths:
    if not path.is_file():
        continue
    lines = path.read_text().splitlines()
    selected = set()
    for i, line in enumerate(lines):
        if any(term in line for term in ('def register_callback', 'def deregister_callback', 'def _on_physics',
                                         'def _on_play', 'def _on_stop', 'PHYSICS_PRE_STEP', 'PHYSICS_POST_STEP',
                                         'def initialize_physics', 'class IsaacEvents')):
            selected.update(range(max(0, i-3), min(len(lines), i+48)))
    print(json.dumps({'path': str(path), 'lines': ['%d: %s' % (i+1, lines[i]) for i in sorted(selected)]}))
