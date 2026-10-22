from pathlib import Path
import json
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02')
record=json.loads((root/'reports/capture_process.json').read_text())
lines=Path(record['log']).read_text(errors='replace').splitlines()
marks=[i for i,l in enumerate(lines) if any(s in l for s in ('Fatal','Segmentation','signo','SIGSEGV','Stack','stack trace','[SV02','Backtrace','backtrace','crash detected'))]
first=next((i for i,l in enumerate(lines) if '[crash]' in l),len(lines))
print(json.dumps({'before_crash':lines[max(0,first-55):first+18]}))
raise SystemExit(0)
selected=sorted({j for i in marks for j in range(max(0,i-10),min(len(lines),i+35))})
print(json.dumps({'context':[lines[i] for i in selected[:200]],'last_before_crash':[l for l in lines if '[crash]' not in l][-50:]}))
