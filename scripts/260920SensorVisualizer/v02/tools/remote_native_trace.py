from pathlib import Path
import json
root=Path('/root/.local/share/ov/data/Kit/Isaac-Sim Full/6.0')
p=root/'1905c6e0-7178-41b4-ed7bc284-c1d08ffa.py.txt'
text=p.read_text(errors='replace') if p.exists() else 'No Python traceback file'
lines=text.splitlines()
indices=[i for i,line in enumerate(lines) if any(s in line for s in ('sensor_visualizer_v02','MainThread','active','get_data'))]
selected=sorted({j for i in indices for j in range(max(0,i-5),min(len(lines),i+15))})
print(json.dumps({'trace':[lines[i] for i in selected[:150]]}))
