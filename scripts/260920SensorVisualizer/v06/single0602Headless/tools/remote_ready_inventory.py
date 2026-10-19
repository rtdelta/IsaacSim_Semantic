import json
from pathlib import Path
import sys
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
rows=[]
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():continue
    try:
        args=[x.decode(errors='replace') for x in (proc/'cmdline').read_bytes().split(b'\0') if x]
        if not args:continue
        cwd=(proc/'cwd').resolve()
        if Path(args[0]).name=='kit' and (proc/'exe').resolve()==Path('/root/isaacsim/kit/kit'):
            entry=args[args.index('--exec')+1] if '--exec' in args else None
            rows.append({'kind':'kit','pid':int(proc.name),'entry':entry,'owned':bool(entry and entry.startswith(str(root)+'/'))})
        elif cwd==root and any(Path(arg).name=='run_web.py' for arg in args[1:]):
            rows.append({'kind':'web','pid':int(proc.name),'cwd':str(cwd)})
    except (OSError,ValueError,IndexError):pass
sys.path.insert(0,str(root))
from single0602_headless.control_ipc import request
output=Path('/root/gpufree-data/semantic/output/sensor_visualizer/single0602Headless')
try:
    status=request(output/'runtime/engine.sock',{'action':'status'},timeout=.5)
    engine={key:status.get(key) for key in ('phase','simulation_state','playing','recording','trajectory_draining','session_id')}
    engine['time_basis_version']=status.get('metadata',{}).get('time_basis_version')
except OSError as exc:engine={'state':'disconnected','error':type(exc).__name__}
print(json.dumps({'processes':rows,'engine':engine}))
