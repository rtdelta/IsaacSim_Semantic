"""Launch only CPU readback/sample/audit work; no second Isaac engine."""
import json
from pathlib import Path
import subprocess
import time
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
out=Path('/root/gpufree-data/semantic/output/single0601ContinuousRt')
stamp=time.strftime('%Y%m%d_%H%M%S')
script=root/'reports'/('cpu_checks_'+stamp+'.sh')
commands=['set -e','cd '+str(root),'source /opt/ros/jazzy/setup.bash',
    '/usr/bin/python3 -B tools/run_acceptance.py '+str(out)+' --output reports/acceptance_actual.json',
    '/usr/bin/python3 -B tools/validate_mcap.py '+str(out/'datasets/recording_12b92d339a94453a8a7b1bb108335fd0')+' --report reports/revalidation_10.json',
    '/usr/bin/python3 -B tools/extract_samples.py '+str(out/'datasets/recording_12b92d339a94453a8a7b1bb108335fd0')+' --output reports/samples/mixed_'+stamp,
    '/usr/bin/python3 -B tools/extract_samples.py '+str(out/'datasets/recording_662cab494f214609813ce64ab99673b2')+' --output reports/samples/geometry_'+stamp]
script.write_text('\n'.join(commands)+'\n')
log=root/'reports'/('cpu_checks_'+stamp+'.log')
with log.open('xb') as f:
    process=subprocess.Popen(['/bin/bash',str(script)],cwd=root,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
receipt={'pid':process.pid,'log':str(log),'created_script':str(script),'samples_relative_paths':['reports/samples/mixed_'+stamp,'reports/samples/geometry_'+stamp]}
(root/'reports/cpu_checks_process.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
