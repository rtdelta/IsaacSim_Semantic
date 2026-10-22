"""Static inspection of installed RTX schemas and annotator definitions only."""
import json,importlib.util
from pathlib import Path
root=Path('/root/isaacsim');found=[]
for base in [root/'exts/isaacsim.sensors.rtx',root/'exts/isaacsim.sensors.rtx.nodes',*list((root/'extscache').glob('isaacsim.sensors.rtx*'))]:
    if not base.is_dir():continue
    for p in base.rglob('*'):
        if not p.is_file() or p.suffix not in ('.py','.ogn'):continue
        if p.stat().st_size>200000:continue
        s=p.read_text(errors='replace')
        if any(k in p.name for k in ('ExtractRTXSensor','GenericModel','LidarOutput','ReadRTX')):
            found.append({'path':str(p),'text':s[:20000]})
        elif p.name in ('extension.py','annotators.py') and 'IsaacExtractRTXSensorPointCloud' in s:
            lines=s.splitlines();hits=[i for i,l in enumerate(lines) if any(k in l for k in ('IsaacExtractRTXSensor','GenericModel','keepOnlyPositiveDistance'))]
            found.append({'path':str(p),'text':'\n'.join('\n'.join(lines[max(0,i-12):i+24]) for i in hits)})
print(json.dumps({'sources':found,'system_scipy':importlib.util.find_spec('scipy') is not None},ensure_ascii=False))
