"""Actual engine regression of unchanged direct/target/periodic and base controls."""
import json,sys,time,uuid,math
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v06');sys.path.insert(0,str(root))
from sensor_visualizer_v06.control_ipc import request
directory=root/'reports/native_owner';owner=json.loads((directory/'owner.json').read_text());sock=owner['socket']
def status():return request(sock,{'action':'status'})
def apply(action,payload=None):
    cid=uuid.uuid4().hex;request(sock,{'action':action,'payload':payload or {},'command_id':cid});end=time.monotonic()+10
    while time.monotonic()<end:
        row=status();receipt=next((v for v in row.get('receipts',[]) if v['command_id']==cid),None)
        if receipt:
            assert receipt['state']=='applied',receipt
            return row
        time.sleep(.01)
    raise TimeoutError(action)
original=status();assert not original['recording'] and not original['playing'],'Run between interactive recording phases'
names=list(original['joint_controls']);checks={}
try:
    apply('hold')
    apply('motion',{'joints':{n:{'mode':'direct','target':.5} for n in names},'tilt':{n:{'mode':'direct','target':.5} for n in ('pitch','roll')}})
    now=status();assert all(abs(v-.5)<1e-4 for v in now['state']['joints_deg'].values());checks['direct']=True
    apply('motion',{'joints':{n:{'mode':'direct','target':0} for n in names},'tilt':{n:{'mode':'direct','target':0} for n in ('pitch','roll')}})
    apply('motion',{'joints':{n:{'mode':'target','target':.5,'speed':20} for n in names},'tilt':{n:{'mode':'target','target':.5,'speed':20} for n in ('pitch','roll')}})
    apply('play');time.sleep(1);apply('pause');now=status()
    assert all(abs(v-.5)<1e-4 for v in now['state']['joints_deg'].values())
    assert all(abs(v['angle']-.5)<1e-4 for v in now['tilt_controls'].values());checks['target']=True
    apply('motion',{'joints':{n:{'mode':'periodic','lower':-.5,'upper':.5,'speed':20} for n in names},
        'tilt':{n:{'mode':'periodic','lower':-.5,'upper':.5,'speed':20} for n in ('pitch','roll')}})
    values={n:[] for n in names+['pitch','roll']};apply('play');end=time.monotonic()+2.5
    while time.monotonic()<end:
        now=status()
        for n in names:values[n].append(now['state']['joints_deg'][n])
        for n in ('pitch','roll'):values[n].append(now['tilt_controls'][n]['angle'])
        time.sleep(.05)
    apply('pause');ranges={n:[min(v),max(v)] for n,v in values.items()}
    assert all(lo>=-.501 and hi<=.501 and lo<-.2 and hi>.2 for lo,hi in ranges.values()),ranges
    checks['periodic_ranges_deg']=ranges;apply('hold');before=status()['state']['position_world_m']
    apply('motion',{'base':{'speed_m_s':.5,'yaw_rate_deg_s':10}});apply('play');time.sleep(1);apply('pause');apply('hold')
    now=status();distance=math.sqrt(sum((a-b)**2 for a,b in zip(before,now['state']['position_world_m'])))
    assert distance>.025,distance;checks['base_velocity_translation_m']=distance
finally:
    apply('pause');apply('hold')
    position=original['state']['position_world_m'];base=original['state']['base_control']
    apply('motion',{'joints':{n:{'mode':'direct','target':v} for n,v in original['state']['joints_deg'].items()},
        'tilt':{n:{'mode':'direct','target':v['angle']} for n,v in original['tilt_controls'].items()},
        'base':{'x':position[0],'y':position[1],'z':position[2],'yaw_deg':base['heading_deg']}})
report={'passed':True,'checks':checks,'scope':'actual GUI owner state; formal capture remains independent'}
(directory/'motion_modes.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
