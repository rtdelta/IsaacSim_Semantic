import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from copy import deepcopy
from unittest.mock import Mock, patch
import numpy as np

from single0602_headless.contracts import load_job
from single0602_headless.frame_contract import CONTRACT, validate_metadata, verify_swing
from single0602_headless.keyboard_control import KeyboardControl
from single0602_headless.native_keyboard import NativeKeyboard
from single0602_headless.robot.base_control import BaseController
from single0602_headless.robot.joint_control import JointController
from single0602_headless.robot.reference_frames import HorizontalFrame
from single0602_headless.trajectory import Trajectory, TrajectoryRecorder, slerp
from single0602_headless.offline_job import snapshot_trajectory


def metadata():
    return dict(CONTRACT, asset_origin_version='test_declared_origin',
        swing_zero_mapping={'native_zero_rad': .2, 'tolerance_rad': 1e-5},
        swing_zero_readback={'native_angle_rad': .2, 'verified': True},
        root_in_reference_row_matrix=np.eye(4).tolist(), joint_definitions=[{'name': 'boom', 'role': 'boom'}],
        asset_manifest={'root_sha256': 'test-only'}, initial_mounts=[], joint_names=['boom'])


def state(t, x=0., revision=0, transition='continuous'):
    return {'schema_version': 1, 'snapshot_id': str(t), 't_sim_s': t,
        'state_revision': 1, 'mount_revision': revision, 'mounts': [],
        'position_world_m': [x, 0., 1.], 'quaternion_xyzw': [0., 0., 0., 1.],
        'joints_deg': {'boom': x}, 'transition_kind': transition}


def motion(heading=0., pitch=0., roll=0.):
    c=BaseController([0.,0.,5.],[1.,0.,0.,0.],0.)
    c.heading=math.radians(heading)
    c.tilt.states['pitch'].angle=pitch
    c.tilt.states['roll'].angle=roll
    joints=JointController({r:0. for r in ('boom','arm','bucket')},
        {r:(-15.,15.) for r in ('boom','arm','bucket')},{r:5. for r in ('boom','arm','bucket')})
    return NS(base_controller=c,controller=joints,config={'joints':[{'name':r,'role':r} for r in joints.states]})


def press(keyboard, keys, source='native', sequence=None):
    if sequence is None:sequence=keyboard.sequences.get(source,0)+1
    return keyboard.update(source,keys,keyboard.input_epoch,sequence)


class CoordinateTests(unittest.TestCase):
    def test_heading_tilt_and_horizontal_diagonal(self):
        for heading in (0.,90.,180.,-90.):
            for pitch,roll in ((0.,0.),(30.,-20.)):
                for keys,direction in ((['W'],0),(['A'],90),(['W','A'],45)):
                    with self.subTest(heading=heading,pitch=pitch,keys=keys):
                        m=motion(heading,pitch,roll);k=KeyboardControl();k.configure({'enabled':True})
                        press(k,keys);k.step(m,1.)
                        a=math.radians(heading+direction)
                        np.testing.assert_allclose(m.base_controller.position,[.5*math.cos(a),.5*math.sin(a),5.],atol=1e-12)

    def test_cancel_vertical_and_combination_order(self):
        m=motion(90.,20.,10.);k=KeyboardControl();k.configure({'enabled':True})
        press(k,['W','S','A','D']);k.step(m,1.)
        np.testing.assert_allclose(m.base_controller.position,[0,0,5])
        press(k,['Z']);k.step(m,1.)
        np.testing.assert_allclose(m.base_controller.position,[0,0,5.5])
        m=motion();press(k,['W','Q']);k.step(m,1.)
        np.testing.assert_allclose(m.base_controller.position,[.5,0,5.])
        k.step(m,1.)
        np.testing.assert_allclose(m.base_controller.position,[.5+.5*math.cos(math.radians(10)),.5*math.sin(math.radians(10)),5.])

    def test_all_joint_pairs_and_clamps(self):
        for positive,negative,role in [('U','J','boom'),('I','K','arm'),('O','L','bucket')]:
            m=motion();k=KeyboardControl();k.configure({'enabled':True});press(k,[positive]);k.step(m,2.)
            self.assertEqual(m.controller.states[role].angle,15.)
            press(k,[negative]);k.step(m,1.);self.assertEqual(m.controller.states[role].angle,5.)
        m=motion();k=KeyboardControl();k.configure({'enabled':True});press(k,['R','T']);k.step(m,1.)
        self.assertEqual(m.base_controller.tilt.states['roll'].angle,10.)
        self.assertEqual(m.base_controller.tilt.states['pitch'].angle,10.)

    def test_horizontal_degeneracy_recovers_and_retains_sign(self):
        h=HorizontalFrame();q=[0,math.sqrt(.5),0,math.sqrt(.5)]
        self.assertFalse(h.update([1,2,3],q)['heading_valid'])
        self.assertEqual(h.last['heading_rad'],0.)
        h.update([1,2,3],[0,0,math.sqrt(.5),math.sqrt(.5)])
        old=h.last['heading_rad'];self.assertFalse(h.update([1,2,3],q)['heading_valid'])
        self.assertAlmostEqual(h.last['heading_rad'],old)
        previous=h.previous_q.copy();result=h.update([1,2,3],[0,0,-math.sqrt(.5),-math.sqrt(.5)])
        self.assertTrue(result['heading_valid']);self.assertGreater(np.dot(previous,h.previous_q),0.)


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.events=[];self.k=KeyboardControl(lambda n,**v:self.events.append((n,v)))
        self.focus={'application_focused':True,'viewport_focused':True,'input_blocked':False,'playing':True}
        self.k.configure({'enabled':True})
        self.adapter=NativeKeyboard(self.k,lambda:self.focus,lambda *a,**k:None,lambda p,**kw:self.k.configure(p))
    def event(self,kind,key):return self.adapter.handle(NS(type=kind,input=key))
    def test_twenty_toggles_do_not_restore_held_or_repeat_input(self):
        for _ in range(20):
            self.event('KEY_PRESS','W');self.assertEqual(self.k.pressed(),{'W'})
            before=self.k.input_epoch;self.k.configure({'enabled':False})
            self.event('KEY_REPEAT','W');self.assertEqual(self.k.pressed(),set())
            self.k.configure({'enabled':True});self.event('KEY_REPEAT','W')
            self.assertEqual(self.k.pressed(),set());self.assertGreater(self.k.input_epoch,before)
        self.assertGreaterEqual(len(self.events),40)
    def test_focus_pause_and_text_input_require_fresh_press(self):
        for field,value in [('application_focused',False),('viewport_focused',False),('input_blocked',True),('playing',False)]:
            self.event('KEY_PRESS','W');self.focus[field]=value;self.adapter.poll_focus()
            self.focus[field]=not value;self.event('KEY_REPEAT','W');self.assertEqual(self.k.pressed(),set())
            self.event('KEY_PRESS','W');self.assertEqual(self.k.pressed(),{'W'})
            self.event('KEY_RELEASE','W')
    def test_epoch_sequence_source_handoff_and_browser_disconnect(self):
        press(self.k,['W'],'web:a',1);old=self.k.input_epoch
        self.event('KEY_PRESS','D');self.assertEqual(self.k.pressed(),{'D'})
        self.assertGreater(self.k.input_epoch,old)
        with self.assertRaises(ValueError):self.k.update('web:a',['W'],old,2)
        press(self.k,[],'web:a',3);self.assertEqual(self.k.pressed(),{'D'})
        with self.assertRaises(ValueError):self.k.update('native',['W'],self.k.input_epoch,1)
    def test_configuration_is_atomic_and_f8_uses_same_entry(self):
        press(self.k,['W']);before=deepcopy(self.k.status())
        with self.assertRaises(ValueError):self.k.configure({'enabled':False,'linear_speed':2,'joint_speed':float('nan')})
        self.assertEqual(before,self.k.status());self.assertEqual(self.k.pressed(),{'W'})
        self.event('KEY_PRESS','F8');self.assertFalse(self.k.enabled)
        self.event('KEY_REPEAT','F8');self.assertFalse(self.k.enabled)
        class Character:
            type='CHAR'
            @property
            def input(self):raise AssertionError('CHAR must not access input')
        self.assertTrue(self.adapter.handle(Character()))


class TrajectoryTests(unittest.TestCase):
    def test_same_file_mixed_modes_events_hold_time_and_snapshot_independence(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);r=TrajectoryRecorder(root/'recorded',metadata())
            r.append(state(5));r.append_event({'event':'keyboard_mode','input_epoch':1,'control_time_s':5.})
            r.append(state(6));r.append(state(7,2,transition='direct'));r.close()
            a=Trajectory.load(r.directory);self.assertEqual(a.duration,2.)
            self.assertEqual(a.sample(.5)['position_world_m'][0],0.)
            self.assertEqual(a.sample(1.999)['position_world_m'][0],0.)
            self.assertEqual(a.sample(2.)['position_world_m'][0],2.)
            self.assertTrue(a.metadata['recording_complete']);self.assertEqual(a.metadata['control_events'],1)
            b=snapshot_trajectory(r.directory,root/'snapshot')
            (r.directory/'states.jsonl').write_text('corrupted')
            self.assertEqual(Trajectory.load(root/'snapshot').states,b.states)
            with self.assertRaises(ValueError):Trajectory.load(r.directory)
    def test_legacy_incomplete_and_wrong_zero_are_rejected(self):
        with self.assertRaises(ValueError):validate_metadata({})
        m=metadata();m['recording_complete']=False
        with self.assertRaises(ValueError):validate_metadata(m,require_complete=True)
        with self.assertRaises(RuntimeError):verify_swing(.21,m['swing_zero_mapping'])
        with self.assertRaises(RuntimeError):verify_swing(float('nan'),m['swing_zero_mapping'])
    def test_mount_boundary_and_quaternion_shortest_path(self):
        self.assertEqual(Trajectory([state(0),state(1,2,revision=1)]).sample(.5)['position_world_m'][0],0.)
        np.testing.assert_allclose(slerp([0,0,0,1],[0,0,0,-1],.5),[0,0,0,1])


class PolicyTests(unittest.TestCase):
    def test_fixed_offline_keepalive_and_baseline_warmup(self):
        job=load_job();self.assertEqual(job['capture']['resource_policy'],'keepalive')
        for override in ({'capture':{'resource_policy':'gated'}},{'replay':{'mode':'live_latest'}},
                         {'scheduling':{'cooperative_yield_ms':1}},{'render':{'camera_subframes':15}}):
            with self.assertRaises(ValueError):load_job(overrides=override)

if __name__=='__main__':unittest.main()
