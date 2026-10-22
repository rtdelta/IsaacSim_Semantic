import json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/reports/unified_bag')
session=Path('/root/gpufree-data/semantic/output/sensor_visualizer/20260922_155355_992974_87bcf8')
result={}
for name,p in [('historical_status',session/'unified_export_status.json'),('acceptance',root/'acceptance/result.json')]:
    if p.exists():
        data=json.loads(p.read_text());result[name]={k:v for k,v in data.items() if k not in ('original_message_digests','output_message_digests')}
for key,p in [('historical_log',root/'historical_pack.log'),('kit_log',root/'acceptance/kit.log')]:
    if p.exists():
        with p.open('rb') as f:f.seek(max(0,p.stat().st_size-5000));result[key]=f.read().decode(errors='replace')
for key,p in [('historical_process',root/'historical_process.json'),('acceptance_process',root/'acceptance/process.json')]:
    if p.exists():
        row=json.loads(p.read_text());folder=Path('/proc')/str(row['pid']);row['exists']=folder.exists()
        if folder.exists():
            parts=(folder/'stat').read_text().split();row['same_identity']=parts[21]==row['start_ticks'];row['state']=parts[2]
        result[key]=row
print(json.dumps(result))
