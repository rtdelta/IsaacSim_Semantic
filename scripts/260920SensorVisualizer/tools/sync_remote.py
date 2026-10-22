"""Reproducible project transfer. Credentials are prompted, never stored."""
import argparse
import getpass
import os
from pathlib import Path, PurePosixPath
import stat
import paramiko

ROOT=Path(__file__).resolve().parents[1]
REMOTE='/root/gpufree-data/semantic/scripts/260920SensorVisualizer'


def mkdirs(sftp,path):
    path=PurePosixPath(path)
    if str(path) in ('/','.'):return
    try:sftp.stat(str(path));return
    except FileNotFoundError:mkdirs(sftp,path.parent);sftp.mkdir(str(path))


def push(client, include_sources=True):
    sftp=client.open_sftp();mkdirs(sftp,REMOTE)
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file() or path.is_symlink():continue
        rel=path.relative_to(ROOT)
        if any(p in ('__pycache__','assets','reports','diagnostics','migration') for p in rel.parts):continue
        if not include_sources and rel.parts[0]=='sources':continue
        target=REMOTE+'/'+rel.as_posix();mkdirs(sftp,PurePosixPath(target).parent)
        # Source identity is checked against SHA-256 by build_asset.py.
        if rel.parts[0]=='sources':
            try:
                if sftp.stat(target).st_size==path.stat().st_size:continue
            except FileNotFoundError:pass
        sftp.put(str(path),target)
        print('UPLOADED',rel.as_posix(),flush=True)
    mkdirs(sftp,REMOTE+'/reports');sftp.close()


def pull(client, reports_only=False):
    sftp=client.open_sftp()
    def folder(remote,local):
        local.mkdir(parents=True,exist_ok=True)
        for item in sftp.listdir_attr(remote):
            src=remote+'/'+item.filename;dst=local/item.filename
            if stat.S_ISDIR(item.st_mode):folder(src,dst)
            elif stat.S_ISREG(item.st_mode):
                sftp.get(src,str(dst));print('DOWNLOADED',dst.relative_to(ROOT).as_posix(),flush=True)
    for name in (('reports',) if reports_only else ('assets','reports')):folder(REMOTE+'/'+name,ROOT/name)
    sftp.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['push','pull'])
    parser.add_argument('--host',default='120.209.70.195');parser.add_argument('--port',type=int,default=30729)
    parser.add_argument('--user',default='root');parser.add_argument('--key');parser.add_argument('--skip-sources',action='store_true');parser.add_argument('--reports-only',action='store_true')
    args=parser.parse_args();client=paramiko.SSHClient();client.load_system_host_keys();client.set_missing_host_key_policy(paramiko.RejectPolicy())
    auth={'key_filename':args.key} if args.key else {'password':getpass.getpass('SSH password: '),'look_for_keys':False,'allow_agent':False}
    client.connect(args.host,port=args.port,username=args.user,timeout=20,**auth)
    try:push(client,not args.skip_sources) if args.action=='push' else pull(client,args.reports_only)
    finally:client.close()
