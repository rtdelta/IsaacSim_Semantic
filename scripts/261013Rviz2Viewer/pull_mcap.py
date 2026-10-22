"""Download the completed 300-group bag using existing Paramiko and audited SFTP."""
import concurrent.futures,datetime,hashlib,json,os,shutil,sys,threading,time,warnings
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parent
DESTINATION=ROOT.parents[1]/'output/20261013_scene18_single06_300_mcap'
REMOTE=PurePosixPath('/root/gpufree-data/semantic/output/261013Rviz2Viewer/20261013_142507_300/capture/captures/20261013_142524_685978_f13b03ee/bag_unified')
sys.path.insert(0,'C:/Users/15452/.codex/skills/cloud-instance-ops/scripts')
from cloud_ops.audit import Audit
from cloud_ops.security import Redactor,WindowsCredentials,private_directory
from cloud_ops.ssh import check_fingerprint,check_identity,remote_python,IDENTITY_SCRIPT
with warnings.catch_warnings():
    warnings.simplefilter('ignore');import paramiko

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while block:=f.read(4*1024**2):h.update(block)
    return h.hexdigest()

def main():
    profile=ROOT.parent/'260920SensorVisualizer/migrations/20261010_dual_gpu/targets.json'
    target=json.loads(profile.read_text())['targets']['isaac-new'];redactor=Redactor()
    kwargs=dict(hostname=target['host'],port=target['port'],username=target['username'],look_for_keys=False,allow_agent=False,timeout=20,banner_timeout=20,auth_timeout=20)
    if target['auth']=='windows-credential':
        credential=WindowsCredentials().read(target['credential_ref']);redactor.add_secret(credential);kwargs['password']=credential
    elif target['auth']=='key':kwargs['key_filename']=target['identity_file']
    else:raise ValueError('Unsupported credential reference')
    audit=Audit(private_directory(Path(os.environ['LOCALAPPDATA'])/'CloudInstanceOps'),redactor,'20261013-pull-single06-300','User-authorized complete project MCAP transfer to local output','sftp-file-transfer',hashlib.sha256(profile.read_bytes()).hexdigest())
    audit_lock=threading.Lock()
    def event(kind,**data):
        with audit_lock:audit.event(kind,**data)
    client=paramiko.SSHClient()
    class Pin(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self,client,hostname,key):check_fingerprint(key,target['host_fingerprint']);audit.event('ssh.host_key.verified',target_alias='isaac-new')
    client.set_missing_host_key_policy(Pin())
    names=['bag_unified_0.mcap','bag_unified_1.mcap','bag_unified_2.mcap','metadata.yaml']
    script="""import hashlib,json
from pathlib import Path
root=Path(REMOTE);names=NAMES
result=[]
for name in names:
    p=root/name
    assert p.is_file() and p.resolve().is_relative_to(root) and not p.is_symlink()
    before=p.stat();h=hashlib.sha256()
    with p.open('rb') as f:
        while block:=f.read(4*1024**2):h.update(block)
    after=p.stat();assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
    result.append({'name':name,'bytes':before.st_size,'mtime_ns':before.st_mtime_ns,'sha256':h.hexdigest()})
print(json.dumps(result))
""".replace('REMOTE',repr(str(REMOTE))).replace('NAMES',repr(names))
    lock=threading.Lock();progress={};channels=[];started=time.monotonic()
    try:
        audit.event('ssh.connect.requested',target_alias='isaac-new',channel='SFTP; ops CLI does not implement SFTP file transfer')
        client.connect(**kwargs)
        response=remote_python(client,IDENTITY_SCRIPT,audit,'identity',20);assert response['exit_code']==0
        check_identity(json.loads(response['stdout']),target);audit.event('ssh.instance.verified',target_alias='isaac-new')
        audit.snapshot('bag_manifest',script);response=remote_python(client,script,audit,'bag-source-manifest',60);assert response['exit_code']==0
        manifest=json.loads(response['stdout']);assert [x['name'] for x in manifest]==names
        total=sum(x['bytes'] for x in manifest);assert total<6*1024**3
        assert DESTINATION.resolve().is_relative_to((ROOT.parents[1]/'output').resolve())
        DESTINATION.mkdir(parents=True,exist_ok=True);bag=DESTINATION/'bag_unified';bag.mkdir(exist_ok=True)
        assert bag.resolve().is_relative_to(DESTINATION.resolve())
        if shutil.disk_usage(DESTINATION).free<total+1024**3:raise RuntimeError('Insufficient local free space')
        source_manifest={'remote':str(REMOTE),'destination':str(bag),'files':manifest,'hash_scope':'Source observation and local equality; not a security certification','audit_log':str(audit.path)}
        (DESTINATION/'source_manifest.json').write_text(json.dumps(source_manifest,indent=2),encoding='utf-8')
        def transfer(item,sftp):
            name=item['name'];dest=bag/name;part=bag/(name+'.download.part')
            if dest.exists():
                if dest.stat().st_size!=item['bytes'] or digest(dest)!=item['sha256']:raise FileExistsError('Different destination file retained: '+str(dest))
                with lock:progress[name]=item['bytes']
                return {'name':name,'status':'already_verified','bytes':item['bytes'],'sha256':item['sha256']}
            assert not part.is_symlink()
            offset=part.stat().st_size if part.exists() else 0
            if offset>item['bytes']:raise ValueError('Oversized partial retained: '+str(part))
            with lock:progress[name]=offset
            remote_name=str(REMOTE/name);sftp.get_channel().settimeout(45)
            st=sftp.stat(remote_name);assert st.st_size==item['bytes'] and st.st_mtime==item['mtime_ns']//10**9
            event('artifact.download.requested',source=remote_name,destination=str(dest),resume_offset=offset,sha256=item['sha256'])
            with sftp.open(remote_name,'rb') as src,part.open('ab') as out:
                # Bounded 32-request batches avoid old Paramiko's unbounded prefetch.
                while offset<item['bytes']:
                    chunks=[(pos,min(32768,item['bytes']-pos)) for pos in range(offset,min(offset+1024**2,item['bytes']),32768)]
                    for (pos,size),data in zip(chunks,src.readv(chunks)):
                        if len(data)!=size:raise IOError('Short source read')
                        out.write(data);offset+=len(data)
                    with lock:progress[name]=offset
                out.flush();os.fsync(out.fileno())
            after=sftp.stat(remote_name);assert after.st_size==item['bytes'] and after.st_mtime==item['mtime_ns']//10**9
            assert part.stat().st_size==item['bytes'] and digest(part)==item['sha256'],'Partial hash mismatch retained for diagnosis'
            if dest.exists():raise FileExistsError('Destination appeared during transfer')
            part.rename(dest);event('artifact.download.verified',destination=str(dest),bytes=item['bytes'],sha256=item['sha256'])
            return {'name':name,'status':'downloaded_verified','bytes':item['bytes'],'sha256':item['sha256']}
        print(json.dumps({'phase':'transfer_started','bytes':total,'destination':str(bag)},ensure_ascii=False),flush=True)
        for _ in manifest:channels.append(client.open_sftp())
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures=[pool.submit(transfer,item,sftp) for item,sftp in zip(manifest,channels)]
            pending=set(futures);last_print=0
            while pending:
                _,pending=concurrent.futures.wait(pending,timeout=5,return_when=concurrent.futures.FIRST_COMPLETED)
                for f in futures:
                    if f.done() and f.exception():client.close();raise f.exception()
                now=time.monotonic()
                if now-last_print>=10 or not pending:
                    with lock:done=sum(progress.values())
                    print(json.dumps({'phase':'progress','bytes':done,'total_bytes':total,'percent':round(100*done/total,2),'elapsed_s':round(now-started,1)},ensure_ascii=False),flush=True);last_print=now
            results=[f.result() for f in futures]
        receipt={**source_manifest,'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'verified':True,'bytes':total,'results':results,'elapsed_s':time.monotonic()-started}
        (DESTINATION/'transfer_receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        (DESTINATION/'README.md').write_text('# Scene18 自制 single06 链路 300 帧 MCAP\n\n'
            '此目录是 2026-10-13 录制包的本地副本。`bag_unified/` 的三个 MCAP 分段和 metadata.yaml 共同构成一个完整 ROS 2 bag。\n\n'
            '300 组，10 Hz 仿真时间采样，13 路点云，4 路鱼眼图像及参数/位姿，TF、关节、整机位姿、Clock 与元数据；32 话题、9006 消息。\n\n'
            '整机 X 0.1 m/s，整机 Yaw/Pitch/Roll 和 boom/arm/bucket 均 ±15°、3°/s 周期运动，cab-track 初始角保持。\n\n'
            '接收端文件大小及 SHA-256 与远端观察值全部相同，见 transfer_receipt.json；源文件保留远端。\n\n'
            '独立回放工具及测试报告见本项目 scripts/261013Rviz2Viewer/README.md 和 docs/ExecutionReport.md。\n',encoding='utf-8')
        audit.finish('succeeded',files=len(results),bytes=total)
        print(json.dumps({'phase':'completed','verified':True,'files':len(results),'bytes':total,'destination':str(DESTINATION),'audit_log':str(audit.path)},ensure_ascii=False),flush=True)
    except BaseException as exc:
        audit.finish('failed',error_type=type(exc).__name__,error=redactor.text(str(exc)));raise
    finally:
        for channel in channels:
            try:channel.close()
            except Exception:pass
        client.close()

if __name__=='__main__':main()
