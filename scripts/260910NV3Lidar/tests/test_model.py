"""Regressions for coordinate mapping, missing returns and seam completion."""
import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nz3_model import (ROWS,COLS,xyz_to_angles,frame_grid,fit_pattern,ideal_grid,directions)
from isaac_utils import box_ranges


class TestModel(unittest.TestCase):
    def test_bag_forward_and_left_axes(self):
        az,el=xyz_to_angles([[0,10,0],[-10,0,0],[0,1,1]])
        np.testing.assert_allclose(az,[0,90,0],atol=1e-10)
        np.testing.assert_allclose(el,[0,0,45],atol=1e-10)

    def test_ranges_do_not_change_sample_direction(self):
        a,e=xyz_to_angles([[1,2,3],[5,10,15]])
        np.testing.assert_allclose(a[0],a[1]);np.testing.assert_allclose(e[0],e[1])

    def test_zero_return_is_not_a_real_beam(self):
        points=np.zeros(2,dtype=[('x','f4'),('y','f4'),('z','f4'),('ring','u2')])
        points[1]=(0,10,0,46)
        a,e,count,stats=frame_grid(points)
        self.assertEqual(np.isfinite(a).sum(),1)
        self.assertEqual(stats['zero_or_nonfinite'],1)
        self.assertEqual(count[46,240],1)
        self.assertFalse(np.isfinite(a[0]).any())

    def test_no_interpolation_across_half_fov_seam(self):
        a=np.full((3,ROWS,COLS),np.nan);e=a.copy()
        a[:,40,100]=-69.75;e[:,40,100]=-5
        a[:,40,350]=55.25;e[:,40,350]=-4
        t=fit_pattern(a,e)
        self.assertAlmostEqual(t['elevation_deg'][40,239],-5)
        self.assertAlmostEqual(t['elevation_deg'][40,240],-4)
        self.assertTrue(np.isfinite(t['directions']).all())
        self.assertEqual(t['source'][40,100],0)
        self.assertEqual(t['source'][40,200],2)

    def test_missing_sector_endpoint_does_not_duplicate_measured_seam(self):
        a=np.full((3,ROWS,COLS),np.nan);e=a.copy()
        a[:,46,238]=-.500001;e[:,46,238]=0
        a[:,46,240]=0;e[:,46,240]=0
        t=fit_pattern(a,e)
        self.assertLess(t['azimuth_deg'][46,239],t['azimuth_deg'][46,240]-.1)
        self.assertEqual(t['azimuth_deg'][46,240],0)  # measured value is preserved

    def test_empty_recording_scaffold_is_complete(self):
        a=np.full((3,ROWS,COLS),np.nan)
        t=fit_pattern(a,a)
        expected_a,expected_e=ideal_grid()
        np.testing.assert_allclose(t['azimuth_deg'],expected_a,atol=1e-5)
        np.testing.assert_allclose(t['elevation_deg'],expected_e,atol=1e-5)
        self.assertTrue((t['source']==4).all())

    def test_ray_box_oracle_handles_parallel_and_inside_rays(self):
        dirs=np.array([[1.,0,0],[0,1,0],[1,1,0]])
        dirs/=np.linalg.norm(dirs,axis=1,keepdims=True)
        np.testing.assert_allclose(box_ranges(dirs,[-10]*3,[10]*3),[10,10,np.sqrt(200)])
        r=box_ranges(dirs,[4.5,-1,-1],[5.5,1,1])
        self.assertEqual(r[0],4.5)
        self.assertTrue(np.isinf(r[1:]).all())


if __name__=='__main__':unittest.main()
