import json,subprocess,sys,time
from pathlib import Path
root=Path(__file__).resolve().parent
cases=json.loads(Path(sys.argv[1]).read_text())
for c in cases:
    name=c["name"];args=c["args"]
    print("START",name,flush=True)
    cp=subprocess.run([sys.executable,str(root/"runner.py"),name,*args],capture_output=True,text=True)
    print("FINISH",name,cp.returncode,cp.stdout[-700:],cp.stderr[-700:],flush=True)
    result=root/"cases"/name/"result.json"
    if result.exists():
        d=json.loads(result.read_text())
        print("RESULT",name,d.get("status"),d.get("error","")[-600:],flush=True)

