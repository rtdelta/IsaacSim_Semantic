"""Audited two-SSH streaming relay; no credentials are sent between instances."""
import hashlib,json,os,queue,shlex,sys,threading,time
from pathlib import Path
import paramiko
skill=Path('C:/Users/15452/.codex/skills/cloud-instance-ops/scripts');sys.path.insert(0,str(skill))
from cloud_ops.audit import Audit
from cloud_ops.security import Redactor,WindowsCredentials,private_directory
from cloud_ops.ssh import check_fingerprint,check_identity,remote_python,collect,OutcomeUnknown
root=Path(__file__).resolve().parent;config=root/'targets.json';policy=json.loads(config.read_text())
redactor=Redactor();provider=WindowsCredentials();values={}
for alias in ('isaac-new','isaac-dual'):
    values[alias]=provider.read(policy['targets'][alias]['credential_ref']);redactor.add_secret(values[alias])
audit=Audit(private_directory(Path(os.environ['LOCALAPPDATA'])/'CloudInstanceOps'),redactor,
    'sensor-visualizer-dual-migration','从单卡迁移可视化资产及必要项目代码，保持原路径并校验所有文件','migration',hashlib.sha256(config.read_bytes()).hexdigest())
clients=[];channels=[];started=time.monotonic();status_path=root/'migration_status.json'
def status(phase,**fields):
    row={'phase':phase,'elapsed_s':time.monotonic()-started,**fields}
    temporary=status_path.with_suffix('.json.part');temporary.write_text(json.dumps(row,indent=2));temporary.replace(status_path)
    print(json.dumps(row),flush=True)
def connect(alias):
    target=policy['targets'][alias];audit.event('ssh.connection.requested',alias=alias,host=target['host'],port=target['port'],auth='credential-reference')
    t=paramiko.Transport((target['host'],target['port']));t.start_client(timeout=15)
    check_fingerprint(t.get_remote_server_key(),target['host_fingerprint']);t.auth_password(target['username'],values.pop(alias))
    c=paramiko.SSHClient();c._transport=t;clients.append(c)
    script="import os,json,hashlib,subprocess\nfrom pathlib import Path\nprint(json.dumps({'hostname':os.uname().nodename,'machine_id_sha256':hashlib.sha256(Path('/etc/machine-id').read_bytes()).hexdigest(),'gpu':subprocess.run(['nvidia-smi','--query-gpu=uuid','--format=csv,noheader'],capture_output=True,text=True,check=True).stdout.strip().splitlines()}))\n"
    result=remote_python(c,script,audit,alias+'-identity',30)
    if result['exit_code']:raise RuntimeError('Identity command failed')
    actual=json.loads(result['stdout']);check_identity(actual,target)
    expected=['GPU-98e8b2c0-e87d-4770-07ca-72683e12547c'] if alias=='isaac-new' else ['GPU-dd705158-62c7-b406-a93d-952e4643bda5','GPU-a9910171-024e-c4ba-faf4-26f8321c7f77']
    if actual['gpu']!=expected:raise RuntimeError('GPU identity changed for '+alias)
    audit.event('instance.identity.verified',alias=alias,**actual);return c
try:
    status('connecting');source=connect('isaac-new');target=connect('isaac-dual')
    graph=remote_python(source,(root/'source_latest_references.py').read_text(),audit,'latest-scene-reference-graph',30)
    if graph['exit_code']:raise RuntimeError('Scene reference probe failed')
    (root/'source_references.json').write_text(graph['stdout'])
    status('preparing_source_archive')
    prep=remote_python(source,(root/'prepare_source_archive.py').read_text(),audit,'source-snapshot',600)
    if prep['exit_code']:raise RuntimeError('Source archive failed: '+prep['stderr'][-1000:])
    meta=json.loads(prep['stdout'].splitlines()[-1]);meta.pop('phase',None)
    (root/'archive_metadata.json').write_text(json.dumps(meta,indent=2))
    work='/root/gpufree-data/.migration_sensor_20261010_dual'
    setup="from pathlib import Path\nimport json\np=Path("+repr(work)+")\np.mkdir(mode=0o700,exist_ok=True)\nm=p/'owner.json'\nv={'task':'sensor-visualizer-dual-migration-20261010'}\nassert not m.exists() or json.loads(m.read_text())==v,'Work ownership conflict'\nm.write_text(json.dumps(v))\nprint(json.dumps({'target_work':str(p)}))\n"
    result=remote_python(target,setup,audit,'target-staging-setup',30)
    if result['exit_code']:raise RuntimeError('Target staging setup failed')
    tsftp=paramiko.SFTPClient.from_transport(target.get_transport());ssftp=paramiko.SFTPClient.from_transport(source.get_transport())
    with tsftp.open(work+'/archive_metadata.json','w') as f:f.write(json.dumps(meta))
    with ssftp.open(work+'/migration_manifest.json','r') as f:manifest_bytes=f.read()
    if hashlib.sha256(manifest_bytes).hexdigest()!=meta['manifest_sha256']:raise RuntimeError('Source manifest mismatch')
    (root/'migration_manifest.json').write_bytes(manifest_bytes)
    reader="import sys\nfrom pathlib import Path\nf=Path("+repr(meta['archive'])+").open('rb')\nfor c in iter(lambda:f.read(1048576),b''):sys.stdout.buffer.write(c)\nsys.stdout.buffer.flush()\n"
    receiver="from pathlib import Path\nimport sys,hashlib,json,os\nw=Path("+repr(work)+")\nm=json.loads((w/'archive_metadata.json').read_text())\np=w/'assets_and_code.tar.gz.part'\nh=hashlib.sha256();n=0\nwith p.open('wb') as f:\n for c in iter(lambda:sys.stdin.buffer.read(1048576),b''):f.write(c);h.update(c);n+=len(c)\nassert n==m['archive_bytes'] and h.hexdigest()==m['archive_sha256'],'Received archive mismatch'\nos.replace(p,w/'assets_and_code.tar.gz')\nprint(json.dumps({'received':n,'archive_sha256':h.hexdigest()}))\n"
    sch=source.get_transport().open_session(window_size=16*1024*1024,max_packet_size=131072)
    tch=target.get_transport().open_session(window_size=16*1024*1024,max_packet_size=131072);channels=[sch,tch]
    sch.settimeout(30);tch.settimeout(30)
    audit.event('stream.transfer.requested',source_archive=meta['archive'],target_work=work,bytes=meta['archive_bytes'],sha256=meta['archive_sha256'],method='bounded-local-two-SSH-relay')
    sch.exec_command('python3 -I -S -B -c '+shlex.quote(reader));tch.exec_command('python3 -I -S -B -c '+shlex.quote(receiver))
    q=queue.Queue(maxsize=8);stop=threading.Event();errors=[]
    def pump():
        try:
            while not stop.is_set():
                block=sch.recv(1048576)
                while not stop.is_set():
                    try:q.put(block or None,timeout=.2);break
                    except queue.Full:pass
                if not block:break
        except Exception as exc:errors.append(exc)
    thread=threading.Thread(target=pump,daemon=True);thread.start()
    done=0;digest=hashlib.sha256();last=time.monotonic();transfer_start=last
    status('transferring',bytes=0,total=meta['archive_bytes'])
    try:
        while True:
            try:block=q.get(timeout=1)
            except queue.Empty:
                if errors:raise errors[0]
                if not thread.is_alive():raise RuntimeError('Source stream stopped unexpectedly')
                continue
            if block is None:break
            tch.sendall(block);done+=len(block);digest.update(block)
            if time.monotonic()-last>5:
                status('transferring',bytes=done,total=meta['archive_bytes'],percent=round(done/meta['archive_bytes']*100,2),mib_s=done/(time.monotonic()-transfer_start)/1024**2);last=time.monotonic()
        if done!=meta['archive_bytes'] or digest.hexdigest()!=meta['archive_sha256']:raise RuntimeError('Relayed source stream mismatch')
        tch.shutdown_write();received=collect(tch,60);sent=collect(sch,30)
        if received['exit_code'] or sent['exit_code']:raise RuntimeError('Remote stream did not finish successfully')
        audit.event('stream.transfer.completed',bytes=done,sha256=digest.hexdigest(),target_receipt=json.loads(received['stdout']))
    finally:stop.set();sch.close();tch.close();thread.join(timeout=5)
    status('validating_and_promoting',files=meta['files'],source_bytes=meta['source_bytes'])
    checked=remote_python(target,(root/'validate_and_promote.py').read_text(),audit,'validate-and-promote',600)
    if checked['exit_code']:raise RuntimeError('Validation/promotion failed: '+checked['stderr'][-1500:])
    result=json.loads(checked['stdout']);(root/'migration_result.json').write_text(json.dumps(result,indent=2))
    # Compare transported active source against the trusted local delivered v06.
    with tsftp.open('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06/deployment_manifest.json','r') as f:deployed=json.loads(f.read())
    rows={r['path']:r for r in json.loads(manifest_bytes)['files']};local_v06=root.parent.parent/'v06';mismatches=[]
    for name,h in deployed.items():
        relative='semantic/scripts/260920SensorVisualizer/v06/'+name
        if rows.get(relative,{}).get('sha256')!=h or not (local_v06/name).is_file() or hashlib.sha256((local_v06/name).read_bytes()).hexdigest()!=h:mismatches.append(name)
    if mismatches:raise RuntimeError('Delivered v06 differs from trusted local code: '+repr(mismatches[:10]))
    provenance={'local_v06_matching_files':len(deployed),'mismatches':mismatches}
    (root/'code_provenance.json').write_text(json.dumps(provenance,indent=2));audit.event('code.provenance.verified',**provenance)
    audit.finish('succeeded');status('finished',**result,**provenance,audit_log=str(audit.path))
except Exception as exc:
    unknown=isinstance(exc,OutcomeUnknown)
    audit.finish('unknown' if unknown else 'failed',error_type=type(exc).__name__,error=redactor.text(str(exc)))
    status('unknown' if unknown else 'failed',error_type=type(exc).__name__,error=redactor.text(str(exc)),audit_log=str(audit.path))
    sys.exit(1)
finally:
    for c in channels:c.close()
    for c in clients:c.close()
