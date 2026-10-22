"""Column-vector rigid transforms and captured USD joint anchors."""
import math
import numpy as np

def pose_matrix(position, xyzw):
    q=np.asarray(xyzw,dtype=float)
    if not np.isfinite(q).all() or abs(np.linalg.norm(q)-1)>1e-4:raise ValueError('Invalid XYZW quaternion')
    x,y,z,w=q;out=np.eye(4);out[:3,3]=position
    out[:3,:3]=[[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                 [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                 [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]]
    return out

def matrix_pose(matrix):
    m=np.asarray(matrix,dtype=float);r=m[:3,:3]
    if m.shape!=(4,4) or not np.isfinite(m).all() or not np.allclose(r.T@r,np.eye(3),atol=1e-4) or np.linalg.det(r)<0:
        raise ValueError('Expected rigid column-vector transform')
    # Symmetric eigensystem stays stable near 180 degrees.
    xx,xy,xz=r[0];yx,yy,yz=r[1];zx,zy,zz=r[2]
    k=np.array([[xx-yy-zz,xy+yx,xz+zx,zy-yz],[xy+yx,yy-xx-zz,yz+zy,xz-zx],
                [xz+zx,yz+zy,zz-xx-yy,yx-xy],[zy-yz,xz-zx,yx-xy,xx+yy+zz]])/3
    _,v=np.linalg.eigh(k);q=v[:,-1]
    if q[3]<0:q=-q
    return m[:3,3].tolist(),q.tolist()

def axis_rotation(axis,angle):
    c,s=math.cos(angle),math.sin(angle);r=np.eye(4)
    if axis=='X':r[:3,:3]=[[1,0,0],[0,c,-s],[0,s,c]]
    elif axis=='Y':r[:3,:3]=[[c,0,s],[0,1,0],[-s,0,c]]
    elif axis=='Z':r[:3,:3]=[[c,-s,0],[s,c,0],[0,0,1]]
    else:raise ValueError('Unknown joint axis '+axis)
    return r

def forward_kinematics(manifest,root,joints):
    bodies={'track_link':np.asarray(root)@np.asarray(manifest['base_in_reference_col'])}
    for joint in manifest['joints']:
        if joint['name'] not in joints:raise ValueError('Missing actual joint '+joint['name'])
        bodies[joint['child']]=bodies[joint['parent']]@np.asarray(joint['parent_anchor_col'])@axis_rotation(joint['axis'],joints[joint['name']])@np.linalg.inv(joint['child_anchor_col'])
    return bodies

def choose_model_group(group,offset,count):
    result=group+offset
    if not 0<=result<count:raise ValueError('Model offset exceeds available groups')
    return result

def deadline_ns(origin,frame_index,rate_hz):
    if rate_hz<=0:raise ValueError('Rate must be positive')
    return int(origin)+round(frame_index*1e9/rate_hz)
