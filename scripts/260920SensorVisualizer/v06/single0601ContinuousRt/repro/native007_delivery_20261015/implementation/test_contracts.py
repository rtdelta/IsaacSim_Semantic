import gzip,unittest,struct
from pathlib import Path
import numpy as np
from tools.native_rotation_localization.normalizer import normalize
from tools.native_rotation_localization.math_independent import decode,pose
from tools.native_instant_baseline.math_independent import decode as old_decode
ROOT=Path(__file__).resolve().parents[2]
class Contracts(unittest.TestCase):
 def test_oblique_spherical_world_and_sensor(self):
  # Analytically known azimuth 30 deg, elevation 30 deg, range 8 m.
  expected=np.array([[6.,2*np.sqrt(3),4.]])
  m=pose(np.deg2rad(5.))
  for reference in (0,1):
   n=normalize({'coordinates_type_code':1,'frame_of_reference_code':reference},[[30.,30.,8.]],m)
   np.testing.assert_allclose(n['native_cartesian'],expected,atol=1e-14)
   np.testing.assert_allclose(n['world'],expected if reference else expected@m[:3,:3],atol=1e-14)
   np.testing.assert_allclose(n['distance'],[8.])
 def test_world_no_double_pose(self):
  m=pose(.2);a=np.array([[3.,4.,5.]])
  n=normalize({'coordinates_type_code':0,'frame_of_reference_code':1},a,m)
  np.testing.assert_array_equal(n['world'],a)
  np.testing.assert_allclose(n['local']@m[:3,:3],a)
 def test_full_old_owned_bytes_regression(self):
  paths=list((ROOT/'reports/remote/reports/native_instant_baseline/native005_20261015_v1/M_E/R3P/r01/q04/continuous/gmo').glob('*.gz'))
  self.assertEqual(len(paths),18)
  for p in paths:
   raw=gzip.decompress(p.read_bytes());h,a,x=decode(raw);oh,oa,ox=old_decode(raw)
   self.assertEqual({k:v for k,v in h.items() if k!='model_to_app_transform'},oh)
   for k in oa:np.testing.assert_array_equal(a[k],oa[k])
   np.testing.assert_array_equal(x,ox)
 def test_declared_span_cannot_use_allocation_tail(self):
  path=next((ROOT/'reports/remote/reports/native_instant_baseline/native005_20261015_v1/M_E/R3P/r01/q04/continuous/gmo').glob('*.gz'))
  b=bytearray(gzip.decompress(path.read_bytes()));struct.pack_into('<Q',b,16,265)
  with self.assertRaises(ValueError):decode(b)
if __name__=='__main__':unittest.main()
