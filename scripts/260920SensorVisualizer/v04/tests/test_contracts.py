import json
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sensor_visualizer_v04.contracts import SampleClock, load_job, assert_frozen
from sensor_visualizer_v04.buffers import SlotPool, array_view, receive_message
from sensor_visualizer_v04.geometry import rigid_pose, matrix_from_pose, OPTICAL_TO_USD
from sensor_visualizer_v04.robot.joint_control import JointController


class Contracts(unittest.TestCase):
    def test_clock_has_no_accumulated_drift(self):
        c=SampleClock(30,133333333)
        self.assertEqual(c.stamp(108000),3600133333333)
        self.assertEqual(c.stamp(3)-c.stamp(0),100000000)
        with self.assertRaises(RuntimeError): assert_frozen(.3,.31)

    def test_incompatible_rates_rejected(self):
        with self.assertRaises(ValueError): load_job(overrides={'sample_hz':17})
        with self.assertRaises(ValueError): load_job(overrides={'motion':{'base':{'z':float('nan')}}})

    def test_slot_lifetime_and_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            pool=SlotPool(Path(tmp)/'slots',1,1024)
            try:
                slot=pool.reserve(0); self.assertIsNone(pool.reserve(1))
                source=np.arange(24,dtype=np.float32).reshape(6,4)
                d=pool.pack(slot,{'cloud':source}); source[:]=-1
                view=array_view(pool.maps[0],d['arrays']['cloud'])
                self.assertEqual(view[5,3],23)
                with self.assertRaises(ValueError): view[0,0]=1
                del view
                with self.assertRaises(RuntimeError): pool.pack(slot,{'huge':np.zeros(1025,dtype=np.uint8)})
                pool.mark_sent(slot)
                pool.release(slot,0,d['generation'])
                slot=pool.reserve(1)
                with self.assertRaises(BufferError): pool.pack(slot,{'huge':np.zeros(1025,dtype=np.uint8)})
                with self.assertRaises(RuntimeError): pool.release(slot,0,d['generation'])
                with self.assertRaises(ValueError): array_view(pool.maps[0],{'dtype':'<f4','shape':[999],'nbytes':3996,'offset':0})
            finally: pool.close()

    def test_fragmented_socket_message(self):
        left,right=socket.socketpair()
        value={'event':'group','name':'partial transport'}
        data=json.dumps(value).encode(); packet=struct.pack('!I',len(data))+data
        def producer():
            for byte in packet: left.sendall(bytes([byte]))
            left.close()
        thread=threading.Thread(target=producer); thread.start()
        try: self.assertEqual(receive_message(right),value)
        finally: right.close(); thread.join()

    def test_pose_roundtrip_and_optical_axes(self):
        for q in ([0,0,0,1],[1,0,0,0],[0,.7071067811865476,0,.7071067811865476]):
            matrix=matrix_from_pose([1,2,3],q)
            p,r=rigid_pose(matrix)
            np.testing.assert_allclose(matrix_from_pose(p,r),matrix,atol=1e-12)
        np.testing.assert_array_equal(np.array([0,0,1,0])@OPTICAL_TO_USD,[0,0,-1,0])

    def test_three_joint_modes_and_atomic_validation(self):
        c=JointController({'boom':0},{'boom':(-30,30)},{'boom':5})
        c.execute({'boom':{'mode':'direct','target':10}},{'boom':0}); self.assertEqual(c.step(0)['boom'],10)
        c.execute({'boom':{'mode':'target','target':12,'speed':5}},{'boom':10})
        self.assertAlmostEqual(c.step(.1)['boom'],10.5); self.assertEqual(c.step(100)['boom'],12)
        c.execute({'boom':{'mode':'periodic','lower':-15,'upper':15,'speed':5}},{'boom':0})
        self.assertEqual(c.step(9)['boom'],-15)
        with self.assertRaises(ValueError): c.execute({'boom':{'mode':'direct','target':100}},{'boom':-15})
        self.assertEqual(c.states['boom'].angle,-15)

if __name__=='__main__': unittest.main()
