"""Pure-math acceptance tests; no Isaac installation required."""
import math
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sensor_visualizer.base_control import BaseController
from sensor_visualizer.cloud_rate import ScanRateGate, on_capture_grid


class BaseTests(unittest.TestCase):
    def create(self):
        return BaseController((3,4,2),(1,0,0,0),0)

    def test_reverse_preserves_height(self):
        c=self.create(); c.velocity(-.5,0); c.step(2)
        self.assertEqual(c.position,(2,4,2))

    def test_arc_independent_of_timestep(self):
        a,b=self.create(),self.create()
        for c in (a,b): c.velocity(2,90)
        a.step(1)
        for _ in range(60): b.step(1/60)
        self.assertAlmostEqual(a.x,3+4/math.pi)
        self.assertAlmostEqual(a.y,4+4/math.pi)
        for x,y in zip(a.position,b.position): self.assertAlmostEqual(x,y)

    def test_turn_retains_initial_tilt(self):
        tilt=(math.cos(.2),math.sin(.2),0,0)
        c=BaseController((0,0,2),tilt,0); c.velocity(0,90); c.step(1)
        q=c.orientation
        # World Z rotation keeps the body's Z-vector's world Z component.
        self.assertAlmostEqual(1-2*(q[1]**2+q[2]**2),math.cos(.4))
        self.assertEqual(c.position,(0,0,2))

    def test_direct_hold_and_reset(self):
        c=self.create(); c.velocity(1,20); c.direct(9,8,-90); c.step(5)
        self.assertEqual(c.position,(9,8,2)); self.assertEqual(c.speed,0)
        c.reset(); self.assertEqual(c.position,(3,4,2)); self.assertEqual(c.orientation,(1,0,0,0))

    def test_invalid_command_is_atomic(self):
        c=self.create()
        with self.assertRaises(ValueError): c.direct(99,float('nan'),0)
        self.assertEqual(c.position,(3,4,2))

    def test_sensor_startup_does_not_change_capture_phase(self):
        early,late=ScanRateGate(10),ScanRateGate(10)
        a=[i for i in range(1,61) if early.accept(i/60,100)]
        b=[i for i in range(17,61) if late.accept(i/60,100)]
        images=[i for i in range(17,61) if on_capture_grid(i/60,10)]
        self.assertEqual(b,images)
        self.assertEqual(b,[i for i in a if i>=17])
        self.assertEqual(len(a),10)
        self.assertFalse(late.accept(1.,100))

    def tilt(self,c,name,mode,**values):
        c.command_tilt('execute',commands={name:dict(mode=mode,**values)})

    def test_direct_tilt_is_immediate_and_preserves_pivot(self):
        c=self.create();self.tilt(c,'pitch','direct',target=12)
        self.tilt(c,'roll','direct',target=-8)
        self.assertEqual(c.position,(3,4,2))
        w,x,y,z=c.orientation
        actual=np.array([[1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y)],
                         [2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x)],
                         [2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)]])
        p,r=math.radians(12),math.radians(-8)
        ry=np.array([[math.cos(p),0,math.sin(p)],[0,1,0],[-math.sin(p),0,math.cos(p)]])
        rx=np.array([[1,0,0],[0,math.cos(r),-math.sin(r)],[0,math.sin(r),math.cos(r)]])
        np.testing.assert_allclose(actual,ry@rx,atol=1e-12)

    def test_relative_zero_restores_authored_orientation(self):
        q=(.98,.1,-.13,.09);q=tuple(a/math.sqrt(sum(v*v for v in q)) for a in q)
        w,x,y,z=q;heading=math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))
        c=BaseController((1,2,3),q,heading)
        self.tilt(c,'roll','direct',target=12);self.tilt(c,'roll','direct',target=0)
        np.testing.assert_allclose(c.orientation,q,atol=1e-14)

    def test_target_tilt_and_translation_run_independently(self):
        c=self.create();c.velocity(1,0)
        self.tilt(c,'pitch','target',target=10,speed=4)
        c.step(2);self.assertEqual(c.tilt_angles()['pitch'],8)
        c.step(1);self.assertEqual(c.tilt_angles()['pitch'],10)
        self.assertFalse(c.tilt.states['pitch'].running)
        self.assertEqual(c.position,(6,4,2))

    def test_two_periodic_tilts_and_timestep_independence(self):
        a,b=self.create(),self.create()
        for c in (a,b):
            self.tilt(c,'pitch','periodic',lower=-5,upper=10,speed=7)
            self.tilt(c,'roll','periodic',lower=-8,upper=4,speed=11)
        a.step(25)
        for _ in range(1500):b.step(1/60)
        for n in ('pitch','roll'):
            self.assertAlmostEqual(a.tilt_angles()[n],b.tilt_angles()[n],places=9)
            self.assertLessEqual(a.tilt.states[n].angle,a.tilt.states[n].upper)
            self.assertGreaterEqual(a.tilt.states[n].angle,a.tilt.states[n].lower)

    def test_height_hold_and_reset(self):
        c=self.create();c.height(3.4);c.velocity(1,8)
        self.tilt(c,'roll','target',target=10,speed=2);c.step(1)
        c.command_tilt('hold',name='roll');c.step(1)
        self.assertEqual(c.tilt_angles()['roll'],2);self.assertEqual(c.z,3.4)
        c.hold();before=c.position;c.step(2);self.assertEqual(c.position,before)
        c.reset();self.assertEqual(c.position,(3,4,2));self.assertEqual(c.tilt_angles(),{'pitch':0,'roll':0})

    def test_invalid_tilt_batch_does_not_partially_apply(self):
        c=self.create()
        with self.assertRaises(ValueError):
            c.command_tilt('execute',commands={'pitch':{'mode':'direct','target':10},
                'roll':{'mode':'target','target':20,'speed':0}})
        self.assertEqual(c.tilt_angles(),{'pitch':0,'roll':0})
        with self.assertRaises(ValueError):c.height(float('nan'))
        self.assertEqual(c.z,2)


if __name__=='__main__': unittest.main()
