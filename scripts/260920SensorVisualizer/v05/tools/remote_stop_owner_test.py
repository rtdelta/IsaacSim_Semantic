import json,os,signal,socket,struct,time
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v05')
info=json.loads((root/'reports/native_owner/owner.json').read_text());pid=info['pid']
proc=Path('/proc')/str(pid)
if proc.exists():
    raw=(proc/'cmdline').read_bytes()
    assert str(root/'kit_interactive_entry.py').encode() in raw,'PID no longer belongs to owner test'
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
            s.settimeout(2);s.connect(info['socket']);m=json.dumps({'action':'close'}).encode();s.sendall(struct.pack('!I',len(m))+m);s.recv(4096)
    except OSError:pass
    end=time.monotonic()+8
    while proc.exists() and (proc/'cmdline').read_bytes() and time.monotonic()<end:time.sleep(.1)
    if proc.exists() and (proc/'cmdline').read_bytes():
        assert str(root/'kit_interactive_entry.py').encode() in (proc/'cmdline').read_bytes()
        os.kill(pid,signal.SIGTERM)
        end=time.monotonic()+20
        while proc.exists() and (proc/'cmdline').read_bytes() and time.monotonic()<end:time.sleep(.1)
        assert not proc.exists() or not (proc/'cmdline').read_bytes(),'Owned test process is still shutting down; postpone restart'
print(json.dumps({'stopped_own_pid':pid}))
