"""Use a one-task, forced-read SSH key to pull the source archive over LAN."""
import hashlib,json,os,subprocess,time,traceback
from pathlib import Path
work=Path('/root/gpufree-data/.migration_sensor_20261010_dual');meta=json.loads((work/'archive_metadata.json').read_text())
started=time.monotonic()
def status(phase,**fields):
    row={'phase':phase,'elapsed_s':time.monotonic()-started,**fields}
    p=work/'direct_status.json';t=p.with_suffix('.json.part');t.write_text(json.dumps(row,indent=2));t.replace(p)
ssh=['ssh','-F','/dev/null','-i',str(work/'source_read_key'),'-o','IdentityAgent=none','-o','IdentitiesOnly=yes',
     '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(work/'source_known_hosts'),
     '-o','GlobalKnownHostsFile=/dev/null','-o','ForwardAgent=no','-o','BatchMode=yes','-o','RequestTTY=no',
     '-o','ClearAllForwardings=yes','-o','ConnectTimeout=15','root@100.122.231.122']
try:
    status('source_identity_probe')
    probe=subprocess.run(ssh+['probe'],capture_output=True,text=True,timeout=30,check=True)
    identity=json.loads(probe.stdout)
    if identity['archive_sha256']!=meta['archive_sha256'] or identity['manifest_sha256']!=meta['manifest_sha256']:raise RuntimeError('Source task/archive identity mismatch')
    status('source_verified',source_archive_sha256=meta['archive_sha256'])
    stderr=(work/'direct_ssh.stderr').open('wb');p=subprocess.Popen(ssh+['read'],stdout=subprocess.PIPE,stderr=stderr)
    part=work/'assets_and_code.direct.tar.gz.part';h=hashlib.sha256();n=0;last=time.monotonic()
    with part.open('wb') as f:
        for c in iter(lambda:p.stdout.read(1048576),b''):
            f.write(c);h.update(c);n+=len(c)
            if time.monotonic()-last>1:
                status('transferring',bytes=n,total=meta['archive_bytes'],percent=round(n/meta['archive_bytes']*100,2),mib_s=n/(time.monotonic()-started)/1024**2);last=time.monotonic()
    code=p.wait(timeout=30);stderr.close()
    if code or n!=meta['archive_bytes'] or h.hexdigest()!=meta['archive_sha256']:raise RuntimeError('Direct SSH transfer integrity failed')
    os.replace(part,work/'assets_and_code.tar.gz');status('validating',bytes=n,archive_sha256=h.hexdigest())
    checked=subprocess.run(['/usr/bin/python3','-I','-S','-B',str(work/'validate_and_promote.py')],capture_output=True,text=True,timeout=600)
    if checked.returncode:raise RuntimeError('Promotion failed: '+checked.stderr[-1500:])
    report=json.loads(checked.stdout);status('finished',**report)
except Exception as exc:
    status('failed',error_type=type(exc).__name__,error=str(exc));traceback.print_exc();raise
