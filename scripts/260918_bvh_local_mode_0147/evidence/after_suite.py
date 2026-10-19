from pathlib import Path
import subprocess,time,sys
root=Path(__file__).resolve().parent
log,expected,manifest=sys.argv[1],int(sys.argv[2]),sys.argv[3]
deadline=time.time()+1800
while time.time()<deadline:
    p=root/log
    if p.exists() and len(p.read_text().splitlines())==expected:break
    time.sleep(2)
else:raise RuntimeError("Prior suite did not finish")
sys.exit(subprocess.run([sys.executable,str(root/"suite_serial.py"),manifest],cwd=root).returncode)
