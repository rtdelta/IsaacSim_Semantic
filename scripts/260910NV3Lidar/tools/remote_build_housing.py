"""Run the housing builder in remote Blender and keep all sources/results locally."""
from datetime import datetime,timezone
import getpass
import json
import os
from pathlib import Path
import shlex
import shutil
import paramiko
from deploy_reference_asset import mkdirs,download_tree

ROOT=Path(__file__).resolve().parents[1]


def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    work='/root/gpufree-data/260910NV3Lidar/housing_build/'+stamp
    output=ROOT/'reports/housing_build'/stamp;output.mkdir(parents=True)
    c=paramiko.SSHClient();c.load_system_host_keys();c.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        c.connect('120.209.70.195',port=30162,username='root',
            password=os.environ.get('NZ3_REMOTE_PASSWORD') or getpass.getpass('SSH password: '),
            timeout=15,look_for_keys=False,allow_agent=False)
        c.get_transport().set_keepalive(20);s=c.open_sftp();mkdirs(s,work)
        s.put(str(ROOT/'tools/build_housing_blender.py'),work+'/build_housing_blender.py')
        cmd='env -u LD_LIBRARY_PATH /opt/blender/blender --background --factory-startup --python '
        cmd+=shlex.quote(work+'/build_housing_blender.py')+' -- --output '+shlex.quote(work+'/output')
        _,out,_=c.exec_command(cmd,timeout=600);out.channel.set_combine_stderr(True)
        with (output/'blender.log').open('w',encoding='utf-8') as log:
            for line in out:
                log.write(line);log.flush()
                if any(k in line for k in ('NZ3_','Error','Error:','Traceback','Saved','Time:')):
                    print(line.rstrip(),flush=True)
        code=out.channel.recv_exit_status()
        download_tree(s,work+'/output',output/'output')
        if code or not (output/'output/perspective.png').exists():raise RuntimeError('Blender build failed; see '+str(output))
        source=ROOT/'source/housing';source.mkdir(parents=True,exist_ok=True)
        geometry=ROOT/'assets/NZ3/geometry';geometry.mkdir(parents=True,exist_ok=True)
        for name in ('NZ3_housing.blend','housing_manifest.json'):
            shutil.copy2(output/'output'/name,source/name)
        shutil.copy2(output/'output/NZ3_housing.usda',geometry/'NZ3_housing.usda')
        result=dict(passed=True,remote_work=work,output=str(output/'output'))
        (ROOT/'reports/housing_build/latest.json').write_text(json.dumps(result,indent=2)+'\n')
        print('NZ3_HOUSING_DOWNLOADED',json.dumps(result),flush=True)
    finally:c.close()


if __name__=='__main__':main()
