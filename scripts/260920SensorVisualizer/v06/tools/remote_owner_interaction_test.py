import json,math,sys,time,uuid
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06');sys.path.insert(0,str(root))
from sensor_visualizer_v06.control_ipc import request
from sensor_visualizer_v06.trajectory import Trajectory
info=json.loads((root/'reports/native_owner/owner.json').read_text());socket=info['socket'];latencies=[]
def status():return request(socket,{'action':'status'})
def apply(action,payload=None):
    cid=uuid.uuid4().hex;start=time.monotonic_ns();request(socket,{'action':action,'payload':payload or {},'command_id':cid})
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        s=status();receipt=next((x for x in s.get('receipts',[]) if x['command_id']==cid),None)
        if receipt:
            assert receipt['state']=='applied',receipt
            latencies.append((receipt['completed_ns']-receipt['accepted_ns'])/1e6);return s
        time.sleep(.01)
    raise TimeoutError(action+' not applied')
s=status();assert s['phase']=='interactive_ready'
initial=s['state'];position=initial['position_world_m'];names=list(s['joint_controls'])
apply('motion',{'joints':{names[0]:{'mode':'direct','target':5}},'tilt':{'pitch':{'mode':'direct','target':3},'roll':{'mode':'direct','target':-2}},
    'base':{'x':position[0]+.2,'y':position[1],'z':position[2]+.1,'yaw_deg':20}})
apply('record_start');apply('keyboard',{'enabled':True,'joint_speed':10,'linear_speed':.5,'angular_speed':10});apply('play')
for _ in range(34):apply('keys',{'source':'web:native-test','keys':['W','Q','U']});time.sleep(.1)
apply('keys',{'source':'web:native-test','keys':[]});apply('pause')
s=status();actual=s['state'];assert actual['joints_deg'][names[0]]>5.1,actual['joints_deg']
assert actual['position_world_m'][0]>position[0]+.21,actual['position_world_m']
mount=next(x for x in actual['mounts'] if x['id']=='MyAiry_front')
apply('mount',{'id':mount['id'],'position_m':[mount['position_m'][0]+.02,*mount['position_m'][1:]],'rotation_deg':mount['rotation_deg']})
camera=next(x for x in status()['state']['mounts'] if x['id']=='camera_front')
assert camera['editable'],'Camera transform not supported'
apply('mount',{'id':camera['id'],'position_m':[camera['position_m'][0]+.01,*camera['position_m'][1:]],'rotation_deg':camera['rotation_deg']})
apply('save_mounts');apply('record_stop')
s=status();trajectory=Trajectory.load(s['trajectory_path'])
assert trajectory.duration>.3 and len(trajectory.states)>10
assert trajectory.states[-1]['mount_revision']>=2
samples=sorted(latencies)
report={'passed':True,'trajectory':s['trajectory_path'],'duration_s':trajectory.duration,'rows':len(trajectory.states),
    'applied_ms_p50':samples[len(samples)//2],'applied_ms_p95':samples[min(len(samples)-1,int(.95*len(samples)))],
    'applied_ms_max':max(samples),'owner_max_ms':s['statistics']['max_owner_ms'],'owner_slow_updates':s['statistics']['slow_updates'],
    'final_position':actual['position_world_m'],'final_joints':actual['joints_deg'],'camera_pose_supported':camera['editable'],
    'gui':info.get('gui',False),'frame_gap_max_ms':s['statistics'].get('frame_gap_max_ms'),
    'note':'Actual engine state application test; human-visible feedback and real native key presses require manual verification'}
(root/'reports/native_owner/interaction.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
