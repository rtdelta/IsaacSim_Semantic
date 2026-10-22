import ast,math,tempfile,unittest
from pathlib import Path
import numpy as np
from tools.native_instant_baseline.math_independent import ranges,pose,geometry,wrap,classify
from tools.native_instant_baseline.io import Sink,verify,rows

class Controls(unittest.TestCase):
    def test_serialized_span_and_allocation_tail(self):
        import struct
        from tools.native_instant_baseline.math_independent import decode
        data=bytearray(389)
        struct.pack_into('<IIIIQI',data,0,0x4e474d4f,1,0,0,389,1)
        struct.pack_into('<16f',data,56,*np.eye(4).reshape(-1));struct.pack_into('<II',data,200,1,1)
        data[284]=64;struct.pack_into('<IfI',data,288,1,0.,39)
        header,arrays,xyz=decode(bytes(data)+bytes(64));self.assertEqual(header['allocation_tail_bytes'],64);self.assertEqual(len(xyz),1)
        with self.assertRaises(ValueError):decode(bytes(data[:-1]))
    def rays(self):
        a=np.linspace(-np.pi,np.pi,4096,endpoint=False);return np.column_stack([np.cos(a),np.sin(a),np.zeros(len(a))])
    def independent_intersections(self,d,y):
        # Scalar line/plane generation, separate from vector slab implementation.
        c,s=math.cos(y),math.sin(y);out=[]
        for v in d:
            x=c*v[0]-s*v[1];yy=s*v[0]+c*v[1]
            out.append(min(t for t in [10/x if x else math.inf,-7/x if x else math.inf,8/yy if yy else math.inf,-11/yy if yy else math.inf] if t>0))
        return np.array(out)
    def test_slab_axis_oblique_and_signs(self):
        d=self.rays()
        for y in [0,math.radians(5),-.1,.2]:np.testing.assert_allclose(ranges(d,pose(y)),self.independent_intersections(d,y),rtol=0,atol=1e-12)
    def test_absolute_and_increment_distinct(self):
        d=self.rays()
        for sign in [1,-1]:
            step=math.radians(.05)*sign;states={i:pose(step*i) for i in range(8)}
            for delay,expected in [(0,'current'),(.5,'half'),(1,'previous1'),(2,'previous2')]:
                fitted=[]
                for i in [5,6]:
                    r=self.independent_intersections(d,(i-delay)*step);g=geometry(d*r[:,None],states[i]);fitted.append(i*step+g['yaw_error_rad'])
                    self.assertAlmostEqual(g['yaw_error_rad'],-delay*step,places=10)
                    self.assertEqual(classify(d,r,states,i)['best_members'],[expected])
                self.assertAlmostEqual(wrap(fitted[1]-fitted[0]),step,places=10)
    def test_static_is_unobservable(self):
        d=self.rays();s={i:pose(.1) for i in range(3)};r=self.independent_intersections(d,.1)
        self.assertEqual(classify(d,r,s,2)['status'],'unobservable')
    def test_fixed_fit_rejects_insufficient_coverage(self):
        g=geometry(np.array([[10.,0.,0.]]*120),pose(0));self.assertIsNone(g['yaw_error_rad'])
    def test_owned_bytes_and_hash_readback(self):
        with tempfile.TemporaryDirectory() as td:
            a=np.arange(256,dtype=np.uint8);s=Sink(td);s.submit('gmo/test.bin.gz',a.tobytes(),True);s.event('events.jsonl',{'n':1});a[:]=0;s.close()
            self.assertEqual(verify(td),2)
            import gzip
            self.assertEqual(gzip.decompress((Path(td)/'gmo/test.bin.gz').read_bytes()),bytes(range(256)))
    def test_minimal_import_boundary(self):
        p=Path(__file__).with_name('run_minimal.py');tree=ast.parse(p.read_text())
        imported=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        self.assertFalse(any(n.startswith(('single0601_continuous_rt','tools.clock_state','tools.experiments','sensor_visualizer_v06')) for n in imported))

if __name__=='__main__':unittest.main()
