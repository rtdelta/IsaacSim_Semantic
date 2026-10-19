import json,subprocess
result=subprocess.run(['hostname','-I'],capture_output=True,text=True,check=True)
print(json.dumps({'instance_addresses':result.stdout.strip().split()}))
