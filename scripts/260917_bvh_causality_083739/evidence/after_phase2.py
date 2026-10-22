import json,subprocess,sys,time
from pathlib import Path
root=Path(__file__).resolve().parent
last=root/"cases/flags_11_gaussian_r1/process.json"
deadline=time.monotonic()+180
while time.monotonic()<deadline:
    if last.exists() and "exit_code" in json.loads(last.read_text()):break
    time.sleep(2)
else:raise RuntimeError("Previous queue has not finished")
subprocess.run([sys.executable,str(root/"queue.py"),str(root/"phase3_flags_off.json")],check=True)

