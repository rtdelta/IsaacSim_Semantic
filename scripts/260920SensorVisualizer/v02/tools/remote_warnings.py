from pathlib import Path
from collections import Counter
import json
import re
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02')
record=json.loads((root/'reports/capture_process.json').read_text())
log=Path(record['log']).read_text(errors='replace')
warnings=[]
for line in log.splitlines():
    if '[Warning]' in line or '[Error]' in line or 'Warning (secondary thread)' in line or 'Warning: in ' in line:
        if '[crash]' not in line: warnings.append(re.sub(r'^.*?\[(Warning|Error)\]',r'[\1]',line))
print(json.dumps({'log':record['log'],'counts':dict(Counter(warnings)),'extra':[line for line in log.splitlines() if any(s in line for s in ('Could not open asset','Unresolved','channels','SV02'))][-30:]}))
