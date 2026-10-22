"""GMO 1.0: degrees/metres and explicit output reference; no pose correction."""
import numpy as np
from .math_independent import quantiles

def normalize(header,elements,source_pose):
    a=np.asarray(elements,dtype=np.float64);m=np.asarray(source_pose,dtype=np.float64)
    if header['coordinates_type_code']==1:
        az,el=np.deg2rad(a[:,0]),np.deg2rad(a[:,1]);distance=a[:,2].copy()
        direction=np.column_stack((np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el)))
        cart=direction*distance[:,None]
    else:
        cart=a.copy();distance=np.linalg.norm(cart,axis=1)
        direction=np.divide(cart,distance[:,None],out=np.zeros_like(cart),where=distance[:,None]>0)
    if header['frame_of_reference_code']==1:
        world=cart;local=(world-m[3,:3])@m[:3,:3].T
    else:
        local=cart;world=local@m[:3,:3]+m[3,:3]
    # Current experiments have zero sensor translation and identity model transform.
    if np.linalg.norm(m[3,:3])>1e-10:raise ValueError('Radial invariant requires origin at zero')
    return {'local':local,'world':world,'distance':distance,'native_cartesian':cart,'native_direction':direction,
        'direction_evidence':'output representation, not an independently observed emitted ray'}

def angle_error(a,b):
    a=np.asarray(a,float);b=np.asarray(b,float)
    a=a/np.linalg.norm(a,axis=1)[:,None];b=b/np.linalg.norm(b,axis=1)[:,None]
    return quantiles(np.arctan2(np.linalg.norm(np.cross(a,b),axis=1),np.sum(a*b,axis=1)))
