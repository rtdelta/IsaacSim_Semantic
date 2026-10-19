"""Gf row-vector matrices and ROS optical frame conversion."""
import numpy as np

OPTICAL_TO_USD = np.diag([1., -1., -1., 1.])


def matrix_from_pose(position, xyzw):
    x, y, z, w = xyzw
    if not np.isclose(np.dot(xyzw, xyzw), 1, atol=1e-5): raise ValueError('Invalid quaternion')
    result = np.eye(4)
    result[:3, :3] = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                              [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                              [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]]).T
    result[3, :3] = position
    return result


def rigid_pose(matrix):
    m = np.asarray(matrix, dtype=float)
    if m.shape != (4, 4) or not np.isfinite(m).all() or not np.allclose(m[:,3], [0,0,0,1], atol=1e-6):
        raise ValueError('Invalid affine transform')
    r = m[:3, :3].T
    if not np.allclose(r.T@r, np.eye(3), atol=2e-4) or not np.isclose(np.linalg.det(r), 1, atol=2e-4):
        raise ValueError('TF contains scale or reflection')
    xx, xy, xz = r[0]; yx, yy, yz = r[1]; zx, zy, zz = r[2]
    k = np.array([[xx-yy-zz, xy+yx, xz+zx, zy-yz], [xy+yx, yy-xx-zz, yz+zy, xz-zx],
                  [xz+zx, yz+zy, zz-xx-yy, yx-xy], [zy-yz, xz-zx, yx-xy, xx+yy+zz]])/3
    _, vectors = np.linalg.eigh(k)
    q = vectors[:, -1]
    if q[3] < 0: q = -q
    return m[3,:3].tolist(), q.tolist()
