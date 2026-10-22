import math
import unittest
from single0601_continuous_rt.motion_controller import MotionController
from single0601_continuous_rt.robot.base_control import BaseController
from single0601_continuous_rt.robot.joint_control import JointController
from single0601_continuous_rt.common import ContractError


class Motion:
    def __init__(self):
        self.base_controller=BaseController((0,0,0),(1,0,0,0),0)
        self.controller=JointController({'boom':0},{'boom':(-90,90)},{'boom':10})
        self.config={'joints':[{'name':'boom','role':'boom'}]}
        self.applies=0
    def command_base(self,action,**v):
        if action=='velocity':self.base_controller.velocity(v['speed'],v['yaw_rate_deg'])
        elif action=='direct':self.base_controller.direct(v['x'],v['y'],v['yaw_deg'])
        elif action=='hold':self.base_controller.hold()
    def command(self,action,**v):
        if action=='hold':self.controller.hold(['boom'],{'boom':self.controller.states['boom'].angle})
        else:self.controller.execute(v['commands'],{'boom':self.controller.states['boom'].angle})
    def _command_angles(self):return [self.controller.states['boom'].angle]
    def _apply_controlled_base(self,angles):self.applies+=1


class Controls(unittest.TestCase):
    def test_physical_integration_and_single_owner(self):
        m=Motion()
        c=MotionController(m)
        c.enqueue('parameters','base_velocity',{'speed_m_s':1.,'yaw_rate_deg_s':0.})
        for step in range(600):c.step(1/60,step,step/60)
        self.assertAlmostEqual(m.base_controller.x,10.)
        self.assertEqual(m.applies,600)
        with self.assertRaises(ContractError):c.step(1/60,599,10.)
    def test_focus_loss_clears_queued_press_before_physics(self):
        m=Motion()
        c=MotionController(m)
        c.enqueue('native_keyboard','keys',{'pressed':['W']})
        c.clear_keys('text_field_focus')
        c.step(1/60,1,0.)
        self.assertEqual(m.base_controller.x,0.)
        self.assertEqual(c.keys,set())
    def test_key_repeat_uses_physical_dt_and_trajectory_simulation_time(self):
        m=Motion()
        c=MotionController(m)
        c.enqueue('native_keyboard','keys',{'pressed':['W','D','U']})
        for step in range(60):c.step(1/60,step,step/60)
        self.assertAlmostEqual(math.hypot(m.base_controller.x,m.base_controller.y),.5)
        self.assertAlmostEqual(m.controller.states['boom'].angle,10.)
        c.enqueue('trajectory','trajectory',{'waypoints':[[0,0,0,0],[4,4,0,20]]})
        c.step(1/60,60,1.)
        c.step(1/60,61,3.)
        self.assertAlmostEqual(m.base_controller.x,2.)
        self.assertAlmostEqual(math.degrees(m.base_controller.heading),10.)
    def test_control_credit_and_invalid_trajectory(self):
        c=MotionController(Motion(),capacity=1)
        c.enqueue('parameters','hold')
        with self.assertRaises(ContractError):c.enqueue('parameters','hold')
        c.step(1/60,1,0)
        c.enqueue('trajectory','trajectory',{'waypoints':[[1,0,0,0],[0,1,0,0]]})
        with self.assertRaises(ContractError):c.step(1/60,2,1/60)

if __name__=='__main__':unittest.main()
