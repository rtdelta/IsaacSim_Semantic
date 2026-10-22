"""Deterministic prescribed trajectory. No Isaac dependency and no wall-clock motion."""
import math

def periodic_degrees(t, amplitude=15.0, speed=3.0):
    # 0 -> +A -> -A -> 0 in 4*A/speed logical seconds.
    phase=(t*speed)%(4*amplitude)
    return phase if phase<=amplitude else 2*amplitude-phase if phase<=3*amplitude else phase-4*amplitude

def multiply_wxyz(a,b):
    w,x,y,z=a;v,i,j,k=b
    return [w*v-x*i-y*j-z*k,w*i+x*v+y*k-z*j,w*j-x*k+y*v+z*i,w*k+x*j-y*i+z*v]

def axis_quaternion(axis,angle):
    half=math.radians(angle)/2
    q=[math.cos(half),0.,0.,0.];q[axis+1]=math.sin(half)
    return q

def trajectory(initial_xyz,initial_wxyz,indices,dt=.1,speed_x=.1):
    rows=[]
    for seq,index in enumerate(indices):
        t=index*dt;angle=periodic_degrees(t)
        # R_world = R_initial * Rz(yaw) * Ry(pitch) * Rx(roll).
        delta=multiply_wxyz(multiply_wxyz(axis_quaternion(2,angle),axis_quaternion(1,angle)),axis_quaternion(0,angle))
        q=multiply_wxyz(initial_wxyz,delta);norm=math.sqrt(sum(v*v for v in q));q=[v/norm for v in q]
        xyz=list(initial_xyz);xyz[0]+=speed_x*t
        rows.append({'seq':seq,'trajectory_sample_index':index,'t_sim_s':t,
            'position_world_m':xyz,'quaternion_xyzw':[q[1],q[2],q[3],q[0]],
            'joints_deg':{name:angle for name in ('boom','arm','bucket')},
            'root_rpy_increment_deg':[angle,angle,angle],'world_x_offset_m':speed_x*t,
            'swing_policy':'hold initial angle','motion_velocity_semantics':'trajectory derivative; actual frozen velocities are zero'})
    return rows
