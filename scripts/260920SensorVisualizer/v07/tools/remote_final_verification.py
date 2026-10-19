"""Verify deployed source, preserved baseline, final evidence and owned process exit."""
import hashlib
import json
from pathlib import Path

root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v07')
baseline=json.loads((root/'baseline_manifest.json').read_text())['sha256']
deployed=json.loads((root/'deployment_manifest.json').read_text())
assert root.resolve()==root
def mismatch(base,manifest):
    return [name for name,digest in manifest.items() if not (base/name).is_file()
            or hashlib.sha256((base/name).read_bytes()).hexdigest()!=digest]
source_errors=mismatch(root,deployed)
baseline_errors=mismatch(root.parent/'v06',baseline)
legacy_imports=[]
for path in (root/'sensor_visualizer_v07').rglob('*.py'):
    for line in path.read_text().splitlines():
        stripped=line.strip()
        if stripped.startswith(('import ','from ')) and 'sensor_visualizer_v0' in stripped and 'sensor_visualizer_v07' not in stripped:
            legacy_imports.append(str(path.relative_to(root)))
active=[]
for path in Path('/proc').glob('[0-9]*/cmdline'):
    try:
        arguments=path.read_bytes().split(b'\0')
        state=path.with_name('stat').read_text().rsplit(')',1)[1].split()[0]
    except OSError:continue
    if state in ('Z','X'):continue
    if any(str(root).encode() in argument for argument in arguments):
        active.append({'pid':int(path.parent.name),'state':state})
units=json.loads((root/'reports/linux_unit_tests.json').read_text())
validation=json.loads((root/'reports/native_validation_result.json').read_text())
directory=Path(validation['directory'])
assert directory.resolve().is_relative_to(Path('/root/gpufree-data/semantic/output/sensor_visualizer/v07_validation'))
summary=json.loads((directory/'evidence_summary.json').read_text())
bad_logs=[row['path'] for row in summary['logging'] if row.get('complete') is not True]
result={'passed':not source_errors and not baseline_errors and not legacy_imports and not active
                and units['exit_code']==0 and validation['state']=='passed' and not bad_logs,
        'deployed_files':len(deployed),'v06_files_checked':len(baseline),'source_mismatch':source_errors,
        'baseline_mismatch':baseline_errors,'legacy_runtime_imports':legacy_imports,'active_v07_processes':active,
        'linux_unit_exit_code':units['exit_code'],'linux_unit_summary':units['stderr'][-180:],
        'last_validation':directory.name,'last_validation_state':validation['state'],
        'diagnostic_summaries':len(summary['logging']),'incomplete_logs':bad_logs,
        'scope':'Project source hash, retained v06 baseline, owned process command paths and latest completed test; not a system security scan'}
(root/'reports/final_verification.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
assert result['passed'], 'Final project verification failed; preserve report and investigate'
