from pathlib import Path
import json
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02')
output={}
for kind in ('quality','ui'):
    process_path=root/f'reports/{kind}_process.json'
    if not process_path.exists(): continue
    process=json.loads(process_path.read_text()); report=root/('reports/quality/report.json' if kind=='quality' else 'reports/ui_test.json')
    row={'process':process,'alive':(Path('/proc')/str(process['pid'])/'cmdline').exists()}
    if report.exists(): row['report']=json.loads(report.read_text())
    row['tail']=Path(process['log']).read_text(errors='replace')[-3000:]
    output[kind]=row
print(json.dumps(output))
