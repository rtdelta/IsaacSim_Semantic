import os, json, subprocess
env=os.environ.copy();env['DISPLAY']=':20'
r=subprocess.run(['xdpyinfo'],env=env,capture_output=True,text=True,timeout=15)
print(json.dumps({'display':':20','exit_code':r.returncode,'stderr':r.stderr[-1500:],'display_accessible':r.returncode==0}))
