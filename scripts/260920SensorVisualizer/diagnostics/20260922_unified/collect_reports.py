import hashlib,json
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
out=root/'reports/unified_bag'
session=Path('/root/gpufree-data/semantic/output/sensor_visualizer/20260922_155355_992974_87bcf8')
accept=json.loads((out/'acceptance/result.json').read_text())
perf=Path(accept['performance'])
objects={
 'historical_export_report.json':json.loads((session/'unified_export_report.json').read_text()),
 'acceptance_result.json':accept,
 'performance_summary.json':json.loads((perf/'summary.json').read_text()),
 'deployment.json':json.loads((out/'deployment.json').read_text()),
}
resources=[json.loads(line) for line in (perf/'resources.jsonl').read_text().splitlines()]
objects['resource_examples.json']=[next((r for r in resources if r.get('phase')==phase),{}) for phase in ('initializing','paused_or_ready','recording','packing')]
objects['historical_files.json']=[dict(name=p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in (session/'bag_unified').iterdir() if p.is_file()]
process=json.loads((out/'acceptance/process.json').read_text());folder=Path('/proc')/str(process['pid'])
objects['final_state.json']=dict(acceptance_process_state=(folder/'stat').read_text().split()[2] if folder.exists() else 'exited',original_kit_exists=Path('/proc/793358').exists(),
    performance_stop_marker=(perf/'stop').exists(),resource_rows=len(resources))
log=(out/'acceptance/kit.log').read_text(errors='replace').splitlines()
objects['log_summary.json']=dict(errors=[line[:1000] for line in log if '[Error]' in line or 'Traceback (most recent call last)' in line],
    warnings=sum('[Warning]' in line for line in log))
print(json.dumps(objects))
