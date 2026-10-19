"""Validate a standard USD reference, deploy to the requested library, then smoke-test it.

Reads the password from NZ3_REMOTE_PASSWORD or an interactive prompt. Existing
destination files are backed up locally before replacement. No Kit instance is restarted.
"""
import argparse
from datetime import datetime,timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import posixpath
import shlex
import stat
import sys
import paramiko
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
DEST='/root/gpufree-data/IsaacSim_Asset/sensor_set/lidar_set/NZ3'
HOUSING=(ROOT/'assets/NZ3/geometry/NZ3_housing.usda').exists()
PACKAGE=('config/NZ3_scan.usda',)+(('geometry/NZ3_housing.usda',) if HOUSING else ())+('README.md','MyNZ3.usda')


def mkdirs(sftp,path):
    current='/'
    for part in path.strip('/').split('/'):
        current=posixpath.join(current,part)
        try:sftp.stat(current)
        except FileNotFoundError:sftp.mkdir(current)


def download_tree(sftp,remote,local):
    local.mkdir(parents=True,exist_ok=True)
    for attr in sftp.listdir_attr(remote):
        if attr.filename in ('.','..') or '/' in attr.filename:raise ValueError('Invalid SFTP child name')
        rp=remote+'/'+attr.filename;lp=local/attr.filename
        if stat.S_ISDIR(attr.st_mode):download_tree(sftp,rp,lp)
        elif stat.S_ISREG(attr.st_mode):sftp.get(rp,str(lp))


def run_check(client,sftp,work,asset,phase,local,smoke=False,scene=None,control=False,preview=False):
    remote_output=work+'/reports/'+phase
    cmd='cd '+shlex.quote(work)+' && timeout 300s bash tools/run_reference_validation.sh --asset '+shlex.quote(asset)
    cmd+=' --output '+shlex.quote(remote_output)+(' --smoke' if smoke else '')
    if scene:cmd+=' --scene '+shlex.quote(scene)
    if control:cmd+=' --occlusion-control'
    if preview:cmd+=' --preview'
    _,stdout,_=client.exec_command(cmd,timeout=330);stdout.channel.set_combine_stderr(True)
    with (local/(phase+'_run.log')).open('w',encoding='utf-8') as log:
        for line in stdout:
            log.write(line);log.flush()
            if any(k in line for k in ('NZ3_','Traceback','Error','error','app ready')):
                print(line.rstrip(),flush=True)
    code=stdout.channel.recv_exit_status()
    try:download_tree(sftp,remote_output,local/phase)
    except FileNotFoundError:pass
    report=local/phase/'validation.json'
    if code or not report.exists() or not json.loads(report.read_text())['passed']:
        raise RuntimeError(f'{phase} failed (exit {code}); see {local}')
    return json.loads(report.read_text())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='120.209.70.195')
    parser.add_argument('--port',type=int,default=30162)
    parser.add_argument('--user',default='root')
    args=parser.parse_args()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    work='/root/gpufree-data/260910NV3Lidar/reference_acceptance/'+stamp
    output=ROOT/'reports/reference_asset'/stamp;output.mkdir(parents=True)
    client=paramiko.SSHClient();client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(args.host,port=args.port,username=args.user,
                       password=os.environ.get('NZ3_REMOTE_PASSWORD') or getpass.getpass('SSH password: '),
                       timeout=15,auth_timeout=15,look_for_keys=False,allow_agent=False)
        client.get_transport().set_keepalive(20);sftp=client.open_sftp()
        for rel in PACKAGE:
            remote=work+'/candidate/NZ3/'+rel;mkdirs(sftp,posixpath.dirname(remote))
            sftp.put(str(ROOT/'assets/NZ3'/rel),remote)
        for name in ('validate_reference_asset.py','run_reference_validation.sh'):
            remote=work+'/tools/'+name;mkdirs(sftp,posixpath.dirname(remote))
            sftp.put(str(ROOT/'tools'/name),remote)
        print('NZ3_CANDIDATE_UPLOADED',work,flush=True)
        backups=[]
        for rel in PACKAGE:
            try:
                existing=sftp.lstat(DEST+'/'+rel)
                if not stat.S_ISREG(existing.st_mode):raise ValueError('Destination is not a regular file: '+rel)
                backup=output/'previous_deployment'/rel;backup.parent.mkdir(parents=True,exist_ok=True)
                sftp.get(DEST+'/'+rel,str(backup));backups.append(rel)
            except FileNotFoundError:pass
        comparison=None
        if HOUSING:
            run_check(client,sftp,work,work+'/candidate/NZ3/MyNZ3.usda','occlusion_control',output,smoke=True,control=True)
            run_check(client,sftp,work,work+'/candidate/NZ3/MyNZ3.usda','housing_smoke',output,smoke=True,preview=True)
            if 'MyNZ3.usda' in backups and 'config/NZ3_scan.usda' in backups:
                for rel in backups:
                    target=work+'/baseline/NZ3/'+rel;mkdirs(sftp,posixpath.dirname(target))
                    sftp.put(str(output/'previous_deployment'/rel),target)
                run_check(client,sftp,work,work+'/baseline/NZ3/MyNZ3.usda','previous_asset',output,smoke=True)
                with np.load(output/'previous_asset/reference_A.npz') as old,np.load(output/'housing_smoke/reference_A.npz') as new:
                    delta=np.linalg.norm(new['xyz_sensor']-old['xyz_sensor'],axis=1)
                assert delta.max()<.0001,f'Housing changed chamber points by {delta.max()}m'
                old_scan=hashlib.sha256((output/'previous_deployment/config/NZ3_scan.usda').read_bytes()).hexdigest()
                new_scan=hashlib.sha256((ROOT/'assets/NZ3/config/NZ3_scan.usda').read_bytes()).hexdigest()
                assert old_scan==new_scan,'Housing update unexpectedly changed the scan configuration'
                comparison=dict(points=len(delta),max_point_difference_m=float(delta.max()),scan_configuration_sha256=new_scan)
                (output/'housing_comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
        full=run_check(client,sftp,work,work+'/candidate/NZ3/MyNZ3.usda','full',output)
        run_check(client,sftp,work,work+'/candidate/NZ3/MyNZ3.usda','reopened',output,
                  scene=full['results']['saved_reference_scene'])
        run_check(client,sftp,work,full['results']['relocated_package_entry'],'relocated',output,smoke=True)
        mkdirs(sftp,DEST)
        for rel in PACKAGE:
            destination=DEST+'/'+rel;mkdirs(sftp,posixpath.dirname(destination))
            temporary=destination+'.upload-'+stamp
            sftp.put(str(ROOT/'assets/NZ3'/rel),temporary)
            sftp.posix_rename(temporary,destination)
        print('NZ3_ASSET_DEPLOYED',DEST,flush=True)
        deployed=run_check(client,sftp,work,DEST+'/MyNZ3.usda','deployed',output,smoke=True)
        _,stdout,stderr=client.exec_command('sha256sum '+' '.join(shlex.quote(DEST+'/'+r) for r in PACKAGE))
        lines=stdout.read().decode().splitlines()
        if stdout.channel.recv_exit_status():raise RuntimeError(stderr.read().decode())
        remote_hashes={line.split(None,1)[1]:line.split(None,1)[0] for line in lines}
        hashes={r:hashlib.sha256((ROOT/'assets/NZ3'/r).read_bytes()).hexdigest() for r in PACKAGE}
        assert all(remote_hashes[DEST+'/'+r]==h for r,h in hashes.items())
        result=dict(passed=True,entry=DEST+'/MyNZ3.usda',utc=stamp,sha256=hashes,
                    backed_up_files=backups,full_acceptance=str(output/'full/validation.json'),
                    reopened_acceptance=str(output/'reopened/validation.json'),
                    relocated_acceptance=str(output/'relocated/validation.json'),
                    deployed_acceptance=str(output/'deployed/validation.json'),remote_work=work,
                    direct_reference_without_nz3_loader=True,
                    mesh='Blender NZ3 visual housing, 71x100x86 mm' if HOUSING else 'empty geometry Xform',
                    housing_comparison=comparison)
        if HOUSING:
            result.update(housing_acceptance=str(output/'housing_smoke/validation.json'),
                          negative_control=str(output/'occlusion_control/validation.json'),
                          isaac_preview=str(output/'housing_smoke/housing_isaac.png'),range_offset_m=.08)
        (output/'deployment.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        (ROOT/'reports/reference_asset/latest.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print('NZ3_DEPLOYMENT_VERIFIED',json.dumps(result),flush=True)
    finally:client.close()


if __name__=='__main__':main()
