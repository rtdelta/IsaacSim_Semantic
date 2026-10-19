"""Upload a verification copy and run a separate headless Isaac Sim process.

Credentials are read from NZ3_REMOTE_PASSWORD or an interactive prompt, never saved.
No existing interactive Isaac Sim process or sensor asset is modified.
"""
import argparse
import getpass
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import shlex
import sys
import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)
import paramiko

ROOT=Path(__file__).resolve().parents[1]


def mkdirs(sftp,path):
    parts=PurePosixPath(path).parts
    current='/'
    for part in parts[1:]:
        current=posixpath.join(current,part)
        try:sftp.stat(current)
        except FileNotFoundError:sftp.mkdir(current)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='120.209.70.195')
    parser.add_argument('--port',type=int,default=30162)
    parser.add_argument('--user',default='root')
    parser.add_argument('--remote-dir',default='/root/gpufree-data/260910NV3Lidar')
    parser.add_argument('--download-only',action='store_true')
    args=parser.parse_args()
    if not args.remote_dir.startswith('/root/gpufree-data/') or '..' in PurePosixPath(args.remote_dir).parts:
        raise ValueError('Verification directory must be a named child of /root/gpufree-data')
    password=os.environ.get('NZ3_REMOTE_PASSWORD') or getpass.getpass('SSH password: ')
    output=ROOT/'reports/isaacsim';output.mkdir(parents=True,exist_ok=True)
    known=ROOT/'reports/remote_known_hosts'
    client=paramiko.SSHClient();client.load_system_host_keys()
    if known.exists():client.load_host_keys(str(known))
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    status=0
    try:
        client.connect(args.host,port=args.port,username=args.user,password=password,timeout=15,
                       auth_timeout=15,look_for_keys=False,allow_agent=False)
        client.save_host_keys(str(known));client.get_transport().set_keepalive(20)
        sftp=client.open_sftp()
        if not args.download_only:
            upload=[ROOT/'isaac_demo.py',ROOT/'isaac_utils.py',ROOT/'nz3_model.py',ROOT/'run_isaac.sh',
                    ROOT/'calibration/rays.npz',ROOT/'calibration/manifest.json']
            upload.extend(p for p in (ROOT/'assets').rglob('*') if p.is_file())
            for file in upload:
                remote=posixpath.join(args.remote_dir,file.relative_to(ROOT).as_posix())
                mkdirs(sftp,posixpath.dirname(remote));sftp.put(str(file),remote)
            mkdirs(sftp,args.remote_dir+'/reports/isaacsim')
            # A prior success must never disguise a failed run.
            for name in ('validation.json','failure.txt'):
                try:sftp.remove(args.remote_dir+'/reports/isaacsim/'+name)
                except FileNotFoundError:pass
                (output/name).unlink(missing_ok=True)
            print(f'UPLOADED_VERIFICATION_COPY {args.remote_dir}',flush=True)
            cmd='cd '+shlex.quote(args.remote_dir)+' && timeout 420s bash run_isaac.sh'
            stdin,stdout,stderr=client.exec_command(cmd,timeout=450)
            stdout.channel.set_combine_stderr(True)
            with (output/'run.log').open('w',encoding='utf-8') as log:
                for line in stdout:
                    log.write(line);log.flush()
                    if any(word in line for word in ('NZ3_', 'Traceback', 'Error', 'error', 'Assertion', 'app ready')):
                        print(line.rstrip(),flush=True)
            status=stdout.channel.recv_exit_status()
            print('REMOTE_EXIT_CODE',status,flush=True)
        for attr in sftp.listdir_attr(args.remote_dir+'/reports/isaacsim'):
            import stat
            if stat.S_ISREG(attr.st_mode):
                sftp.get(args.remote_dir+'/reports/isaacsim/'+attr.filename,str(output/attr.filename))
        print('DOWNLOADED_RESULTS',output,flush=True)
        if not (output/'validation.json').exists():
            print('NZ3_VALIDATION_FAILED: no successful render report',flush=True)
            status=status or 1
        elif not json.loads((output/'validation.json').read_text(encoding='utf-8')).get('passed'):
            status=status or 1
    finally:
        client.close()
    return status


if __name__=='__main__':
    sys.exit(main())
