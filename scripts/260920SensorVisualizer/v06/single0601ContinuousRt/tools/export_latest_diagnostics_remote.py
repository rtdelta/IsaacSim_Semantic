"""CPU samples and read-only static evidence checks; published data stays immutable."""
import json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
output=Path('/root/gpufree-data/semantic/output/single0601ContinuousRt/datasets')
stamp=time.strftime('%Y%m%d_%H%M%S')
script=root/'reports'/('diagnostic_cpu_'+stamp+'.sh')
samples='reports/samples/noiseless_fast_'+stamp
lines=['set -e','cd '+str(root),'source /opt/ros/jazzy/setup.bash',
    '/usr/bin/python3 -B tools/extract_samples.py '+str(output/'recording_f8eef4b3e9514dcbab71817c1def9c3a')+' --output '+samples,
    '/usr/bin/python3 -B tools/validate_mcap.py '+str(output/'recording_895a415b01434e2d834e11478ca97e3f')+' --report reports/revalidation_original_static.json']
script.write_text('\n'.join(lines)+'\n')
log=root/'reports'/('diagnostic_cpu_'+stamp+'.log')
with log.open('xb') as f:
    process=subprocess.Popen(['/bin/bash',str(script)],cwd=root,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
receipt={'pid':process.pid,'log':str(log),'created_script':str(script),'samples_relative_paths':[samples]}
(root/'reports/cpu_checks_process.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
