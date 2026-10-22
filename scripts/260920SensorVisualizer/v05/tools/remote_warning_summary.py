import json,re
from collections import Counter
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v05');out={}
for track in (root/'reports/native_owner').glob('*_task.json'):
    info=json.loads(track.read_text());p=Path(info['directory'])/'kit.log';counts=Counter()
    for line in p.read_text(errors='replace').splitlines():
        if '[Warning]' in line:
            line=line.split('[Warning]',1)[1].strip();line=re.sub(r'0x[0-9a-fA-F]+','<address>',line)
            counts[line[:350]]+=1
    out[info['mode']+'_'+info['task_id']]={'total_warnings':sum(counts.values()),'distinct_warnings':len(counts),
        'most_common':[{'message':k,'count':v} for k,v in counts.most_common(12)]}
(root/'reports/native_owner/warning_summary.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
