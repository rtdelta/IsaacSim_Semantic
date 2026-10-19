"""Local synthetic UI fixture; never use this entry for production control."""
import sys,tempfile
from pathlib import Path
from dataclasses import asdict
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from sensor_visualizer_v06.web_service import WebService,serve
from sensor_visualizer_v06.robot.base_control import BaseController
from sensor_visualizer_v06.robot.joint_control import JointController
class Fixture(WebService):
    def _poll(self):pass
    def command(self,m):
        if m['action']=='keyboard':self.engine['keyboard_enabled']=m['payload']['enabled']
        if m['action']=='play':self.engine.update(playing=True,motion_state='running')
        if m['action']=='pause':self.engine.update(playing=False,motion_state='paused')
        if m['action']=='stop':self.engine.update(playing=False,motion_state='stopped')
        if m['action']=='exit':self.engine.update(playing=False,phase='exited',motion_state='exited')
        if m['action']=='reinitialize':self.engine.update(playing=False,phase='interactive_ready',motion_state='paused')
        if m['action']=='motion' and m['payload'].get('base'):
            v=m['payload']['base'];self.engine['state']['position_world_m']=[v.get(k,0) for k in ('x','y','z')]
        self.engine.setdefault('receipts',[]).append({'command_id':m.get('command_id'),'action':m['action'],'state':'applied'})
        return {'state':'queued','command_id':m.get('command_id')}
service=Fixture(ROOT,Path(tempfile.gettempdir())/'sv06_ui_fixture','not-used')
c=BaseController([0,0,0],[1,0,0,0],0);j=JointController({'boom':0,'arm':0,'bucket':0},{n:(-180,180) for n in ('boom','arm','bucket')},{n:5 for n in ('boom','arm','bucket')})
service.engine={'phase':'interactive_ready','motion_state':'paused','playing':False,'keyboard_enabled':True,'state':{'t_sim_s':0,'position_world_m':[0,0,0],
    'base_control':c.snapshot(),'mounts':[{'id':'MyAiry_front','reference':'/World/Excavator/swing_link','editable':True,'position_m':[1,0,2],'rotation_deg':[0,0,0]}]},
    'joint_controls':{n:asdict(s) for n,s in j.states.items()},'tilt_controls':{n:asdict(s) for n,s in c.tilt.states.items()},'statistics':{'max_owner_ms':3.2}}
serve(service,port=17877)
