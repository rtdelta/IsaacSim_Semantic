"""Use an installed Linux Isaac USD SDK without starting Kit or downloading anything."""
import argparse
import os
from pathlib import Path
import subprocess

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--isaac-root',type=Path,default=Path('/root/isaacsim'))
    parser.add_argument('script',type=Path)
    parser.add_argument('args',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    root=args.isaac_root.resolve()
    candidates=sorted((root/'extscache').glob('omni.usd.libs-*/pxr'))
    if not candidates: raise SystemExit('Existing USD SDK was not found; nothing is installed automatically.')
    sdk=candidates[-1].parent
    env=os.environ.copy()
    for name in ('PYTHONHOME','PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','VIRTUAL_ENV','CONDA_PREFIX'): env.pop(name,None)
    env['LD_LIBRARY_PATH']=':'.join(map(str,(root/'kit/python/lib',root/'kit',sdk/'bin',sdk/'lib')))
    paths=[sdk,root/'kit/python/lib/python3.12/site-packages',*sorted((root/'extscache').glob('omni.kit.pip_archive-*/pip_prebundle'))]
    code='import sys,runpy\nsys.path[:0]='+repr([str(p) for p in paths if p.is_dir()])+'\n'
    code+='sys.argv='+repr([str(args.script.resolve()),*args.args])+'\nrunpy.run_path(sys.argv[0],run_name="__main__")\n'
    p=subprocess.run([str(root/'kit/python/bin/python3'),'-I','-S','-B','-'],input=code,text=True,env=env)
    raise SystemExit(p.returncode)

if __name__=='__main__': main()
