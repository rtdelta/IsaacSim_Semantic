import json,socket,struct
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v05')
info=json.loads((root/'reports/native_owner/owner.json').read_text())
try:
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as conn:
        conn.settimeout(3);conn.connect(info['socket']);m=json.dumps({'action':'status'}).encode();conn.sendall(struct.pack('!I',len(m))+m)
        def read(n):
            out=b''
            while len(out)<n:
                b=conn.recv(n-len(out))
                if not b:raise EOFError()
                out+=b
            return out
        status=json.loads(read(struct.unpack('!I',read(4))[0]))
    print(json.dumps({'connected':True,'phase':status.get('phase'),'error':status.get('error'),
        'control_time_s':status.get('state',{}).get('t_sim_s'),'mounts':len(status.get('state',{}).get('mounts',[])),
        'statistics':{k:v for k,v in status.get('statistics',{}).items() if not k.endswith('samples')},
        'trajectory':status.get('trajectory_path')},ensure_ascii=False))
except Exception as exc:
    log=Path(info['log']).read_text(errors='replace')
    print(json.dumps({'connected':False,'process_exists':Path('/proc/'+str(info['pid'])).exists(),'error':str(exc),'log_tail':log[-10000:]}))
