"""UI command latency includes IPC accepted-to-applied; no browser network claim."""
import json,os,subprocess,sys,time,uuid
from pathlib import Path
from .runner import ROOT,prepare,run,write
from .resources import Sampler
from .analysis import stats

def run_interaction(spec,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(ROOT/'frozen_runtime'))
    from sensor_visualizer_v06.control_ipc import request
    from run_capture import launch_spec
    args,env,install=launch_spec(ROOT/'frozen_runtime/config/offline.json',gui=True,entry=ROOT/'kit_owner_entry.py')
    env['SL06_OWNER_DIR']=str(directory)
    # Linux AF_UNIX paths are limited to 108 bytes, including terminator.
    socket_path=Path('/root/gpufree-data/semantic/output/single06_lab')/('ctl_'+uuid.uuid4().hex[:12]+'.sock')
    env['SL06_OWNER_SOCKET']=str(socket_path)
    if len(os.fsencode(socket_path))>=108:raise RuntimeError('Control socket path exceeds AF_UNIX limit')
    displays=sorted(Path('/tmp/.X11-unix').glob('X[0-9]*'))
    if not displays:raise RuntimeError('No existing X display for interactive viewport trial')
    env['DISPLAY']=':'+displays[0].name[1:]
    log=(directory/'engine.log').open('xb')
    process=subprocess.Popen(args,cwd=install,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    sampler=Sampler(directory,directory/'kit.pid');sampler.start();child=None
    result={'directory':str(directory),'spec':spec,'scope':'Local IPC accepted-to-applied; excludes web transport and perceived viewport latency'}
    def command(action,payload=None):
        cid=uuid.uuid4().hex
        request(socket_path,{'action':action,'payload':payload or {},'command_id':cid})
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            state=request(socket_path,{'action':'status'})
            receipt=next((r for r in state.get('receipts',[]) if r['command_id']==cid),None)
            if receipt:
                if receipt['state']!='applied':raise RuntimeError(str(receipt))
                state['_lab_receipt']=dict(receipt)
                return state,(receipt['completed_ns']-receipt['accepted_ns'])/1e6
            time.sleep(.01)
        raise TimeoutError('Control receipt timeout')
    try:
        deadline=time.monotonic()+180
        while not (directory/'owner_ready.json').is_file():
            if process.poll() is not None:raise RuntimeError('Owner exited during initialize')
            if time.monotonic()>deadline:raise TimeoutError('Owner initialization')
            time.sleep(.1)
        initial,_=command('play');latency=[];gaps=[];owner=[];last=initial['statistics']['updates']
        result['initial_control_state']=initial.get('control',initial.get('state'))
        if spec.get('concurrent',False):
            capture=directory/'capture';capture_spec=directory/'capture_spec.json'
            write(capture_spec,{**spec,'name':'concurrent_capture','groups':spec.get('groups',4)})
            with (directory/'capture_supervisor.log').open('xb') as capture_log:
                child=subprocess.Popen(['/usr/bin/python3','-u','-m','lab.runner','--spec',str(capture_spec),
                    '--output',str(capture),'--allow-coexisting'],cwd=ROOT,stdin=subprocess.DEVNULL,
                    stdout=capture_log,stderr=capture_log,start_new_session=True)
        start=time.monotonic()
        with (directory/'commands.jsonl').open('x',encoding='utf-8') as commands:
            while (child is not None and child.poll() is None) or (child is None and time.monotonic()-start<spec.get('seconds',30)):
                if time.monotonic()-start>600:raise TimeoutError('Interaction trial time limit')
                tick=time.monotonic();keys=['W','Q','U'] if int(tick-start)%5<3 else []
                state,ms=command('keys',{'source':'web:single06-lab','keys':keys});latency.append(ms)
                st=state['statistics'];count=max(0,st['updates']-last);last=st['updates']
                if count:gaps.extend(st['frame_gap_samples'][-count:]);owner.extend(st['owner_ms_samples'][-count:])
                commands.write(json.dumps({'host_monotonic_ns':time.monotonic_ns(),'applied_ms':ms,'updates':last,'keys':keys,
                    'accepted_ns':state['_lab_receipt']['accepted_ns'],'completed_ns':state['_lab_receipt']['completed_ns']})+'\n')
                time.sleep(max(0,.1-(time.monotonic()-tick)))
        command('keys',{'source':'web:single06-lab','keys':[]})
        result['final_control_state']=state.get('control',state.get('state'))
        result.update(wall_s=time.monotonic()-start,accepted_to_applied_ms=stats(latency),frame_gap_ms=stats(gaps),owner_callback_ms=stats(owner))
        if child:result['capture_result']=json.loads((directory/'capture/result.json').read_text())
        result['passed']=not child or child.returncode==0
    except Exception as exc:result.update(passed=False,error=type(exc).__name__+': '+str(exc))
    finally:
        if child and child.poll() is None:
            write(directory/'capture/control.json',{'action':'stop'})
            try:child.wait(timeout=90)
            except subprocess.TimeoutExpired:child.terminate();child.wait(timeout=20)
        if process.poll() is None:
            try:command('close');process.wait(timeout=30)
            except (OSError,TimeoutError,subprocess.TimeoutExpired):
                process.terminate()
                try:process.wait(timeout=15)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        sampler.close();log.close();write(directory/'interaction_result.json',result)
        if socket_path.exists():socket_path.unlink()
    return result
