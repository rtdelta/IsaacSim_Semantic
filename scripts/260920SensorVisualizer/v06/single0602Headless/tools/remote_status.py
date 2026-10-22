"""Read this project's process identity, native report and bounded error context."""
import json
from pathlib import Path

root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
result={}
record=root/'reports/acceptance_process.json'
if record.is_file():
    info=json.loads(record.read_text());p=Path('/proc',str(info['pid']),'cmdline')
    result['acceptance_pid']=info['pid']
    result['acceptance_running']=p.exists() and info['entry'].encode() in p.read_bytes()
report=root/'reports/isaac_acceptance.json'
if report.is_file():result['acceptance']=json.loads(report.read_text())
log=root/'reports/isaac_acceptance.log'
if log.is_file():
    text=log.read_text(errors='replace').splitlines()
    result['log_tail']=text[-18:]
print(json.dumps(result,ensure_ascii=False))
