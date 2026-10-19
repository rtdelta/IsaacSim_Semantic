import json, os, subprocess, sys
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer')
libs=sorted(Path('/root/isaacsim/extscache').glob('omni.usd.libs-*'))[-1]
env=dict(os.environ)
env['LD_LIBRARY_PATH']=str(next(libs.rglob('libusd_tf.so')).parent)+':/root/isaacsim/kit/lib'
r=subprocess.run([sys.executable,'-B',str(root/'tools/restore_background_options.py'),
    '--expected-sha256','dd7fa9efa0d5edf6e4ddef4bff42555023b22d4705efed1d6c6e0293f07abb41'],
    env=env,capture_output=True,text=True,timeout=50)
print(json.dumps(dict(exit_code=r.returncode,stdout=r.stdout,stderr=r.stderr)))
raise SystemExit(r.returncode)
