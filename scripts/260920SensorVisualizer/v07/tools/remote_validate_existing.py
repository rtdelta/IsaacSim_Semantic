"""Validate every finished bag independently of an unrelated owner failure."""
import json
import subprocess
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v07')
base=Path('/root/gpufree-data/semantic/output/sensor_visualizer/v07_validation')
results=[]
for name in ('20261010_164756','20261010_170650'):
    directory=base/name
    report=json.loads((directory/'validation_result.json').read_text())
    for case in report['results']:
        if not case.get('session') or not case.get('groups'):continue
        command=['/bin/bash','--noprofile','--norc','-c',
            'source /opt/ros/jazzy/setup.bash && exec /usr/bin/python3 -B "$@"','sv07-validate',
            str(root/'tools/validate_capture_data.py'),case['session']]
        process=subprocess.run(command,capture_output=True,text=True,timeout=300)
        row={'run':name,'case':case['case'],'groups':case['groups'],'exit_code':process.returncode}
        if process.returncode:row['error']=process.stderr[-3000:]
        else:row['data_validation']=json.loads(process.stdout.split('VALIDATION_JSON=')[-1])
        results.append(row)
        (directory/'completed_bag_validation.json').write_text(json.dumps([r for r in results if r['run']==name],indent=2))
        print(json.dumps({key:row.get(key) for key in ('run','case','groups','exit_code','error')}),flush=True)
(root/'reports/completed_bag_validation.json').write_text(json.dumps(results,indent=2))
assert all(row['exit_code']==0 for row in results),'One or more bags failed validation'
