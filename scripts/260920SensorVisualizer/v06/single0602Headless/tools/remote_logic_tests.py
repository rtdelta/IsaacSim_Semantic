"""Run portable tests on target Linux, including the actual Unix-domain socket test."""
import json
from pathlib import Path
import subprocess
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/single0602Headless')
result=subprocess.run(['/usr/bin/python3','-B','-m','unittest','discover','-s','tests','-v'],cwd=root,capture_output=True,text=True,timeout=30)
(root/'reports/linux_tests.txt').write_text(result.stdout+'\n'+result.stderr)
report={'exit_code':result.returncode,'tail':(result.stdout+'\n'+result.stderr).splitlines()[-8:]}
(root/'reports/linux_tests.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
raise SystemExit(result.returncode)
