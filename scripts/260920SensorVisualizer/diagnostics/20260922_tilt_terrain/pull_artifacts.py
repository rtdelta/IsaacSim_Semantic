"""Pull only this task's generated artifacts; pinned SSH + existing audit module."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import warnings

SCRIPTS=Path('C:/Users/15452/.codex/skills/cloud-instance-ops/scripts')
sys.path.insert(0,str(SCRIPTS))
from cloud_ops.audit import Audit
from cloud_ops.security import Redactor,WindowsCredentials,load_policy,private_directory
from cloud_ops.ssh import check_fingerprint,check_identity,remote_python,IDENTITY_SCRIPT
with warnings.catch_warnings():
    warnings.simplefilter('ignore');import paramiko

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
config=SCRIPTS/'config.json';policy=load_policy(config);target=policy['targets']['isaac-new']
state=private_directory(Path(os.environ['LOCALAPPDATA'])/'CloudInstanceOps')
redactor=Redactor();secret=WindowsCredentials().read(target['credential_ref']);redactor.add_secret(secret)
audit=Audit(state,redactor,'tilt-terrain-20260922','Retrieve self-generated terrain and validation artifacts',
            'project_sftp_pull',hashlib.sha256(config.read_bytes()).hexdigest())
class Pinned(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self,client,hostname,key):
        check_fingerprint(key,target['host_fingerprint'])
        audit.event('ssh.host_key.verified',fingerprint=target['host_fingerprint'])
client=paramiko.SSHClient();client.set_missing_host_key_policy(Pinned())
remote='/root/gpufree-data/semantic/scripts/260920SensorVisualizer'
asset='/root/gpufree-data/IsaacSim_Asset/environment_module_set/UndulatingGround_20260922'
scene='/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_16_terrain_fisheye.usda'
manifest=[]
try:
    audit.event('sftp.connect.requested',target_alias='isaac-new',direction='remote_to_local',
                coverage='explicit SFTP file transfers; self-generated artifacts, not external downloads')
    client.connect(target['host'],port=target['port'],username=target['username'],password=secret,
                   look_for_keys=False,allow_agent=False,timeout=15,banner_timeout=15,auth_timeout=15)
    result=remote_python(client,IDENTITY_SCRIPT,audit,'identity',15)
    if result['exit_code']:raise RuntimeError('Identity probe failed')
    check_identity(json.loads(result['stdout']),target)
    audit.event('ssh.instance.verified',target_alias='isaac-new')
    sftp=client.open_sftp();sftp.get_channel().settimeout(40)
    files=[(asset+'/'+n,ROOT/'assets/UndulatingGround_20260922'/n)
           for n in ['terrain.blend','terrain.usdc','terrain_config.json','build_report.json']]
    files.append((scene,ROOT/'reports/tilt_terrain'/PurePosixPath(scene).name))
    for name in ['assembly.json','validation.json','recording_check.json','log_summary.json',
                 'cloud_diagnostic.json','blender_build.log','stage_build.log','kit.log']:
        src=remote+'/reports/tilt_terrain/'+name
        try:sftp.stat(src)
        except FileNotFoundError:continue
        files.append((src,ROOT/'reports/tilt_terrain'/name))
    validation_path=remote+'/reports/tilt_terrain/validation.json'
    with sftp.open(validation_path,'rb') as f:validation=json.loads(f.read())
    for label in ['initial_snapshot','final_snapshot']:
        folder=validation.get(label)
        if not folder:continue
        if not folder.startswith(remote+'/reports/tilt_terrain/recordings/camera_snapshots/'):
            raise ValueError('Unexpected snapshot path')
        for cid in ['front','rear','left','right']:
            for name in ['image.png','frame.json','calibration.json']:
                files.append((folder+'/'+cid+'/'+name,ROOT/'reports/tilt_terrain'/label/cid/name))
    for src,dst in files:
        if not dst.resolve().is_relative_to(ROOT.resolve()):raise ValueError('Outside local project')
        audit.event('sftp.file.requested',source=src,destination=str(dst))
        dst.parent.mkdir(parents=True,exist_ok=True)
        temp=dst.with_name(dst.name+'.sftp-part');sftp.get(src,str(temp))
        h=hashlib.sha256()
        with sftp.open(src,'rb') as f:
            while True:
                chunk=f.read(262144)
                if not chunk:break
                h.update(chunk)
        actual=hashlib.sha256(temp.read_bytes()).hexdigest()
        if actual!=h.hexdigest():raise ValueError('Transfer mismatch: '+src)
        temp.replace(dst)
        row={'source':src,'destination':str(dst),'sha256':actual,'size':dst.stat().st_size}
        manifest.append(row);audit.event('sftp.file.verified',**row)
    sftp.close();audit.finish('succeeded',files=len(manifest))
    (ROOT/'reports/tilt_terrain/artifact_transfer.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({'files':len(manifest),'audit_log':str(audit.path)}))
except Exception as exc:
    audit.finish('failed',error=str(exc));raise
finally:client.close()
