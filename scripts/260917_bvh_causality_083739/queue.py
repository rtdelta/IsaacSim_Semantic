import json,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parent
for c in json.loads(Path(sys.argv[1]).read_text()):
 print("START",c["name"],flush=True)
 cp=subprocess.run([sys.executable,str(root/c.get("runner","runner_seed.py")),c["name"],*c["args"]],capture_output=True,text=True)
 print("FINISH",c["name"],cp.stdout[-500:],cp.stderr[-300:],flush=True)
 p=root/"cases"/c["name"]/"result.json"
 if p.exists():
  r=json.loads(p.read_text())
  print("RESULT",c["name"],r["status"],r.get("error","")[-700:],flush=True)
 else:print("NO_RESULT",c["name"],flush=True)

