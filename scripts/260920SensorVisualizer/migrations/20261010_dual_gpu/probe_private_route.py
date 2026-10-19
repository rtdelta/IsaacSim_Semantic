import json,socket
result={'source_address':'100.122.231.122','source_port':22}
try:
    with socket.create_connection((result['source_address'],22),timeout=5) as s:
        s.settimeout(5);result['ssh_reachable']=s.recv(128).startswith(b'SSH-')
except OSError as exc:result.update(ssh_reachable=False,error=type(exc).__name__)
print(json.dumps(result))
