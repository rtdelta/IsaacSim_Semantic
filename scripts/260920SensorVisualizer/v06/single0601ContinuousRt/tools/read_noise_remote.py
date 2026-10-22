"""Bounded installed SDK schema and scalar noise attributes, no model edits."""
import json
from pathlib import Path
root=Path('/root/isaacsim')
hits=[]
for top in ('exts','extscache'):
    for folder in (root/top).glob('*sensor*'):
        for p in folder.rglob('*'):
            if p.is_file() and p.suffix in ('.py','.json','.usda','.md','.html') and p.stat().st_size<2000000:
                data=p.read_text(errors='replace')
                if 'rangeAccuracyM' in data:
                    pos=data.find('rangeAccuracyM')
                    hits.append({'path':str(p),'snippet':data[max(0,pos-350):pos+900]})
                if len(hits)>=6:break
        if len(hits)>=6:break
    if len(hits)>=6:break
print(json.dumps({'installed_sdk_range_accuracy':hits}))
