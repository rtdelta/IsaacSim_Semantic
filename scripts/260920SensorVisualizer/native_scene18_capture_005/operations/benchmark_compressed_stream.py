import hashlib,json,os,sys,time,warnings
from pathlib import Path
sys.path.insert(0,'C:/Users/15452/.codex/skills/cloud-instance-ops/scripts')
from cloud_ops.audit import Audit
from cloud_ops.security import Redactor,WindowsCredentials,private_directory
from cloud_ops.ssh import check_fingerprint,check_identity,remote_python,IDENTITY_SCRIPT
with warnings.catch_warnings():
 warnings.simplefilter('ignore');import paramiko
root=Path(__file__).resolve().parent.parent
profile=root.parent/'migrations/20261010_dual_gpu/targets.json';target=json.loads(profile.read_text())['targets']['isaac-new'];redactor=Redactor()
audit=Audit(private_directory(Path(os.environ['LOCALAPPDATA'])/'CloudInstanceOps'),redactor,'scene18-handoff-download-20261013','Measure bounded lossless-compressed SSH stream throughput for the same authorized MCAP; no remote changes','project-read-stream',hashlib.sha256(profile.read_bytes()).hexdigest())
client=paramiko.SSHClient()
class Pin(paramiko.MissingHostKeyPolicy):
 def missing_host_key(self,client,hostname,key):check_fingerprint(key,target['host_fingerprint'])
client.set_missing_host_key_policy(Pin())
secret=WindowsCredentials().read(target['credential_ref']);redactor.add_secret(secret)
try:
 client.connect(hostname=target['host'],port=target['port'],username=target['username'],password=secret,look_for_keys=False,allow_agent=False,timeout=15,banner_timeout=15,auth_timeout=15)
 identity=remote_python(client,IDENTITY_SCRIPT,audit,'identity',15);check_identity(json.loads(identity['stdout']),target)
 source="import sys,zlib\nc=zlib.compressobj(1)\nwith open('/root/gpufree-data/semantic/output/native_scene18_capture_005/capture_20261012_111643/delivery_300/bag/bag_0.mcap','rb') as f:\n f.seek(1024**3)\n for _ in range(32):sys.stdout.buffer.write(c.compress(f.read(1024**2)))\n sys.stdout.buffer.write(c.flush())\n"
 audit.snapshot('stream_read_request',source)
 ch=client.get_transport().open_session(window_size=16*1024**2,max_packet_size=128*1024);ch.settimeout(60);ch.exec_command('python3 -I -S -B -');ch.sendall(source.encode());ch.shutdown_write()
 start=time.monotonic();h=hashlib.sha256();total=0
 while True:
  block=ch.recv(1024**2)
  if not block:break
  total+=len(block);h.update(block)
 exitcode=ch.recv_exit_status();elapsed=time.monotonic()-start
 result={'bytes':total,'seconds':elapsed,'MiB_per_s':total/1024**2/elapsed,'sha256':h.hexdigest(),'exit':exitcode,'sample_uncompressed_bytes':32*1024**2,'ratio':total/(32*1024**2)}
 assert total>0 and exitcode==0
 audit.finish('succeeded',result=result);print(json.dumps(result))
except BaseException as exc:
 audit.finish('failed',error=redactor.text(str(exc)));raise
finally:client.close()
