import json
import math
from pathlib import Path
import tempfile
import socket
import time
import unittest
from sensor_visualizer_v06.trajectory import Trajectory,TrajectoryRecorder,slerp
from sensor_visualizer_v06.control_ipc import ControlEndpoint,request
from sensor_visualizer_v06.keyboard_control import KeyboardControl
from sensor_visualizer_v06.robot.joint_control import JointController
from sensor_visualizer_v06.robot.base_control import BaseController

def state(t,x=0,transition='continuous',rev=0):
    return {'schema_version':1,'snapshot_id':str(t),'t_sim_s':t,'state_revision':1,'mount_revision':rev,
        'position_world_m':[x,0,0],'quaternion_xyzw':[0,0,0,1],'joints_deg':{'boom_joint':x},
        'mounts':[{'id':'lidar','position_m':[rev,0,0],'rotation_deg':[0,0,0]}],'transition_kind':transition}

class Motion:
    def __init__(self):
        self.base_controller=BaseController([0,0,0],[1,0,0,0],0)
        self.controller=JointController({'boom_joint':0},{'boom_joint':(-15,15)},{'boom_joint':5})
        self.config={'joints':[{'name':'boom_joint','role':'boom'}]}

class Tests(unittest.TestCase):
    def test_interpolation_and_step(self):
        a,b=state(0,0),state(1,10)
        self.assertEqual(Trajectory([a,b]).sample(.5)['position_world_m'][0],5)
        b['transition_kind']='direct'
        self.assertEqual(Trajectory([a,b]).sample(.999)['position_world_m'][0],0)
        self.assertEqual(Trajectory([a,b]).sample(1)['position_world_m'][0],10)
    def test_mount_revision_is_not_interpolated(self):
        row=Trajectory([state(0,0,rev=0),state(1,10,rev=1)]).sample(.5)
        self.assertEqual(row['mount_revision'],0);self.assertEqual(row['position_world_m'][0],0)
    def test_quaternion_shortest_path(self):
        q=slerp([0,0,0,1],[0,0,0,-1],.5)
        self.assertAlmostEqual(abs(q[3]),1)
        q=slerp([0,0,0,1],[0,0,1,0],.5)
        self.assertAlmostEqual(q[2],math.sqrt(.5))
    def test_duplicate_time_uses_latest(self):
        self.assertEqual(Trajectory([state(0,0),state(0,1),state(1,2)]).sample(0)['position_world_m'][0],1)
    def test_invalid_time(self):
        with self.assertRaises(ValueError):Trajectory([state(1),state(0)])
        with self.assertRaises(ValueError):Trajectory([state(float('nan'))])
    def test_disk_and_csv_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'trajectory';r=TrajectoryRecorder(p,{'joint_names':['boom_joint'],'initial_mounts':state(0)['mounts']})
            r.append(state(7,0));r.append(state(8,10,rev=1));r.close()
            a=Trajectory.load(p);self.assertEqual(a.duration,1)
            self.assertEqual(a.states[-1]['mounts'][0]['position_m'][0],1)
            meta=json.loads((p/'metadata.json').read_text());self.assertTrue(meta['recording_complete'])
            b=Trajectory.from_csv((p/'trajectory.csv').read_text(),meta)
            self.assertEqual(b.sample(.5)['joints_deg'],a.sample(.5)['joints_deg'])
    def test_keyboard_combination_clamp_release(self):
        m=Motion();k=KeyboardControl();k.enabled=True;k.update('web:test',['W','D','U']);k.step(m,1)
        self.assertAlmostEqual(math.hypot(m.base_controller.x,m.base_controller.y),.5)
        self.assertLess(m.base_controller.y,0)
        self.assertEqual(m.controller.states['boom_joint'].angle,10)
        k.step(m,1);self.assertEqual(m.controller.states['boom_joint'].angle,15)
        k.update('web:test',[]);self.assertFalse(k.step(m,1))
        k.update('web:test',['W']);k.sources['web:test']=(set(['W']),time.monotonic()-1)
        self.assertFalse(k.step(m,1))
    @unittest.skipUnless(hasattr(socket,'AF_UNIX'),'Unix-domain IPC is tested on the target Linux instance')
    def test_ipc_receipts_and_owned_state(self):
        with tempfile.TemporaryDirectory() as temp:
            endpoint=ControlEndpoint(Path(temp)/'c.sock')
            try:
                s={'phase':'ready','value':[1]};endpoint.publish(s);s['value'][0]=2
                self.assertEqual(request(endpoint.path,{'action':'status'})['value'],[1])
                receipt=request(endpoint.path,{'action':'play','command_id':'test'})
                self.assertEqual(receipt['state'],'queued')
                cmd=endpoint.commands.get(timeout=1);endpoint.result(cmd,'applied')
                self.assertEqual(request(endpoint.path,{'action':'status'})['receipts'][-1]['state'],'applied')
            finally:endpoint.close()

if __name__=='__main__':unittest.main()
