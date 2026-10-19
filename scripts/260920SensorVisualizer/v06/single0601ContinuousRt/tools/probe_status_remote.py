"""Read only the task-owned probe status and bounded task log tail."""
import json
import subprocess
from pathlib import Path

root = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0601ContinuousRt')
receipt = json.loads((root/'reports/probe_process.json').read_text())
pid = receipt['pid']
alive = Path('/proc')/str(pid)
latest = root/'reports/latest_probe.json'
out = {'pid': pid, 'alive': alive.exists(), 'latest': json.loads(latest.read_text()) if latest.exists() else None}
if alive.exists():
    stats = (alive/'stat').read_text().split()
    out['process_state'] = {'state':stats[2], 'cpu_ticks':stats[13:15], 'threads':stats[19], 'rss_pages':stats[23], 'wchan':(alive/'wchan').read_text().strip()}
out['gpu_processes'] = subprocess.run(['nvidia-smi','--query-compute-apps=pid,process_name,used_memory','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=15).stdout
log = Path(receipt['log'])
with log.open('rb') as f:
    f.seek(max(0, log.stat().st_size-2500))
    out['log_tail'] = f.read().decode('utf-8', 'replace')
if out['latest']:
    folder = Path(out['latest']['directory'])
    out['capabilities'] = json.loads((folder/'capabilities.json').read_text())
    out['errors'] = json.loads((folder/'probe_errors.json').read_text())[:5]
else:
    folders = sorted((root/'reports').glob('probe_*'))
    folders = [p for p in folders if p.is_dir()]
    if folders:
        folder = folders[-1]
        out['partial_probe'] = str(folder)
        if (folder/'probe_errors.json').exists():
            errors = json.loads((folder/'probe_errors.json').read_text())
            out['error_count'] = len(errors)
            out['errors'] = errors[:4]
        if (folder/'probe_receipts.json').exists():
            rows = json.loads((folder/'probe_receipts.json').read_text())
            out['receipt_count'] = len(rows)
            out['receipt_examples'] = rows[:2]
print(json.dumps(out))
