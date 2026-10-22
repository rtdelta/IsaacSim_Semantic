"""Exact dirty checks; a new native step always reapplies prescribed state."""
import numpy as np
class MotionUpdateCache:
    def __init__(self):self.invalidate();self.applied=0;self.skipped=0
    def invalidate(self):self.root=self.angles=None;self.native_time=None
    def changes(self,position,orientation,angles,native_time):
        root=np.concatenate((np.asarray(position,dtype=np.float64),np.asarray(orientation,dtype=np.float64)))
        angles=np.asarray(angles,dtype=np.float64)
        clock_changed=self.native_time!=native_time
        return (clock_changed or self.root is None or not np.array_equal(root,self.root),
                clock_changed or self.angles is None or not np.array_equal(angles,self.angles),clock_changed)
    def commit(self,position,orientation,angles,native_time):
        self.root=np.concatenate((np.asarray(position,dtype=np.float64),np.asarray(orientation,dtype=np.float64))).copy()
        self.angles=np.asarray(angles,dtype=np.float64).copy();self.native_time=native_time;self.applied+=1
