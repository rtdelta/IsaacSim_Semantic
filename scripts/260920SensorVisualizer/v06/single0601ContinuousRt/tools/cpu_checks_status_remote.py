import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
receipt=json.loads((root/'reports/cpu_checks_process.json').read_text())
process=Path('/proc')/str(receipt['pid'])
state=(process/'stat').read_text().split()[2] if process.exists() else None
out={'receipt':receipt,'process_state':state,'alive':process.exists() and state!='Z','log_tail':Path(receipt['log']).read_text(errors='replace')[-6000:]}
for relative in receipt['samples_relative_paths']:
    manifest=root/relative/'samples_manifest.json'
    if manifest.exists():
        r=json.loads(manifest.read_text())
        out[relative]={'selected_group_ids':r['selected_group_ids'],'files':len(r['files'])}
if (root/'reports/acceptance_actual.json').exists():
    r=json.loads((root/'reports/acceptance_actual.json').read_text())
    out['acceptance']={k:r[k] for k in ('milestones','accepted_recordings','accepted_groups','all_ready_integrity_ok','full_project_accepted')}
print(json.dumps(out))
