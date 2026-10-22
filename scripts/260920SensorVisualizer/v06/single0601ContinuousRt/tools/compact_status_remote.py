"""Compact observation of existing task-owned engine, worker and immutable results."""
import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
receipt=json.loads((root/'reports/record_process.json').read_text())
process=Path('/proc')/str(receipt['pid'])
state=(process/'stat').read_text().split()[2] if process.exists() else None
matrix=json.loads((root/'reports/acceptance_matrix_actual.json').read_text())
rows=[]
for row in matrix['results']:
    short={k:row.get(k) for k in ('test_case','recording_id','status')}
    short['resources_after']=row.get('gui_resources_after_case')
    path=Path(row['directory'])
    for name in ('lifecycle.json','geometry_diagnostics.json','performance.json'):
        if (path/name).exists():
            r=json.loads((path/name).read_text())
            short[name]=r.get('geometry_diagnostics',r.get('passed',r.get('throughput')))
    rows.append(short)
print(json.dumps({'pid':receipt['pid'],'alive':process.exists() and state!='Z','state':state,'matrix_run_id':matrix.get('run_id'),
                  'all_cases_executed':matrix['all_requested_cases_executed'],'results':rows}))
