from pathlib import Path
import json
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02')
process=json.loads((root/'reports/capture_process.json').read_text())
output=Path('/root/gpufree-data/semantic/output/sensor_visualizer/v02')
sessions=sorted(output.glob('20*'))[-2:] if output.exists() else []
rows=[]
for folder in sessions:
    row={'path':str(folder)}
    for name in ('session.json','writer_report.json'):
        if (folder/name).is_file(): row[name]=json.loads((folder/name).read_text())
    if (folder/'record_worker.log').exists(): row['worker_tail']=(folder/'record_worker.log').read_text(errors='replace')[-5000:]
    if (folder/'performance/summary.json').exists(): row['performance']=json.loads((folder/'performance/summary.json').read_text())
    rows.append(row)
log=Path(process['log']).read_text(errors='replace')
diagnostics=[line for line in log.splitlines() if '[SV02 POSE DIAGNOSTIC]' in line]
print(json.dumps({'process':process,'alive':(Path('/proc')/str(process['pid'])/'cmdline').exists(),
    'diagnostics':diagnostics,'log_tail':log[-8000:],'sessions':rows}))
