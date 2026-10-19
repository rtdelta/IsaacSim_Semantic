"""Run three paired independent processes; preserve every failed run."""
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent
def write(p,x):p.write_text(json.dumps(x,indent=2))
def kits():
    out=[]
    for p in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            if p.read_bytes().split(b'\0')[0].endswith(b'/kit/kit'):out.append(int(p.parent.name))
        except OSError:pass
    return out
def main():
    latest=json.loads((R/'reports/latest.json').read_text());out=Path(latest['directory']);snap=out/'baseline_pose'
    assert json.loads((snap/'ready.json').read_text())['ready']
    if kits():raise RuntimeError('Existing Kit was not stopped')
    dependencies=json.loads((snap/'dependencies.json').read_text());scene='/root/gpufree-data/IsaacSim_Asset/combine_stage/combine_scene_18_terrain_fisheye_mesh.usda'
    source_manifest={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in R.rglob('*') if p.is_file() and p.suffix in ('.py','.json','.md') and not any(x in p.relative_to(R).parts for x in ('reports','deploy_history','__pycache__','operations'))}
    write(out/'source_manifest.json',source_manifest)
    progress={'state':'running','pid':os.getpid(),'completed':[],'current':None,'planned_cases':6};write(out/'progress.json',progress)
    try:
        for repeat in range(3):
            for family in (('legacy','native') if repeat%2==0 else ('native','legacy')):
                if kits():raise RuntimeError('Unexpected live Kit')
                if shutil.disk_usage(out).free<40*1024**3:raise RuntimeError('Insufficient free disk')
                case=out/family/f'round_{repeat+1:02d}';case.mkdir(parents=True,exist_ok=False)
                if family=='legacy':
                    spec={'name':'NC006_static','pose':'static','trajectory':str(snap),'groups':3,'timeout_s':600,'policy':'keepalive','scene':scene}
                    path=case/'input_spec.json';write(path,spec)
                    args=['/usr/bin/python3','-u','-m','lab.runner','--spec',str(path),'--output',str(case/'capture')];cwd=R/'legacy'
                else:
                    spec=json.loads((R/'native/config/baseline.json').read_text());spec.update(scene=scene,scene_sha256=dependencies[scene],trajectory=str(snap/'states.jsonl'),trajectory_sha256=hashlib.sha256((snap/'states.jsonl').read_bytes()).hexdigest(),source_dependencies_sha256=dependencies,measure_frames=3,timeout_s=600,motion='static',motion_profile='NC006_actual_initial_pose',output_root=str(out),expected_lidars=13,expected_cameras=4)
                    path=case/'input_spec.json';write(path,spec)
                    args=['/usr/bin/python3','-u',str(R/'native/run.py'),'--config',str(path),'--output',str(case/'capture')];cwd=R/'native'
                progress['current']={'family':family,'round':repeat+1,'directory':str(case)};write(out/'progress.json',progress)
                with (case/'supervisor.log').open('xb') as log:
                    child=subprocess.Popen(args,cwd=cwd,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
                    progress['current']['pid']=child.pid;write(out/'progress.json',progress);rc=child.wait()
                progress['completed'].append({'family':family,'round':repeat+1,'exit_code':rc,'directory':str(case)});progress['current']=None;write(out/'progress.json',progress)
                if rc:raise RuntimeError(f'{family} round {repeat+1} failed; evidence preserved')
        changed=[p for p,h in dependencies.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h]
        progress.update(state='completed',dependencies_changed=changed,remaining_kit=kits());write(out/'progress.json',progress)
        if changed:raise RuntimeError('Source asset changed during experiment')
    except BaseException as exc:
        progress.update(state='failed',error=type(exc).__name__+': '+str(exc));write(out/'progress.json',progress);raise
if __name__=='__main__':main()
