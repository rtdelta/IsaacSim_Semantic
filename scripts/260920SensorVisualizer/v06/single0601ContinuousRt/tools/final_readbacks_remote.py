"""Read-only full MCAP checks with independent revised feature detection."""
import json,subprocess,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
output=Path('/root/gpufree-data/semantic/output/single0601ContinuousRt/datasets')
stamp=time.strftime('%Y%m%d_%H%M%S')
script=root/'reports'/('final_readbacks_'+stamp+'.sh')
lines=['set -e','cd '+str(root),'source /opt/ros/jazzy/setup.bash']
for name,recording in [('noiseless_fast','recording_f8eef4b3e9514dcbab71817c1def9c3a'),('noiseless_static','recording_c7199891357b4981aa30878e838a427d'),
                       ('full_100','recording_04340e89046a43878e845c5131e4dad0')]:
    lines.append('/usr/bin/python3 -B tools/validate_mcap.py '+str(output/recording)+' --report reports/revalidation_'+name+'.json')
script.write_text('\n'.join(lines)+'\n')
log=root/'reports'/('final_readbacks_'+stamp+'.log')
with log.open('xb') as f:
    process=subprocess.Popen(['/bin/bash',str(script)],cwd=root,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
receipt={'pid':process.pid,'log':str(log),'created_script':str(script),'samples_relative_paths':[]}
(root/'reports/cpu_checks_process.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
