from pathlib import Path
import json,subprocess,time,sys
root=Path(__file__).resolve().parent
deadline=time.time()+900
while time.time()<deadline:
    p=root/"stage1_camera_abc_status.jsonl"
    if p.exists() and len(p.read_text().splitlines())==3:break
    time.sleep(2)
else:raise RuntimeError("First suite did not finish")
cp=subprocess.run([sys.executable,str(root/"suite_serial.py"),"stage1_remaining.json"],cwd=root)
sys.exit(cp.returncode)
