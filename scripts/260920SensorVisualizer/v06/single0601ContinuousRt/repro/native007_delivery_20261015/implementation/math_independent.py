"""Independent numeric oracle: row-vector USD matrices and six infinite inner planes."""
import math,struct
import numpy as np
BOUNDS=np.array([[-7.,10.],[-11.,8.],[-4.,6.]])

def quantiles(x):
    x=np.asarray(x,float).reshape(-1)
    if not len(x):return None
    return {str(q):float(np.partition(x,max(0,math.ceil(q*len(x))-1))[max(0,math.ceil(q*len(x))-1)]) for q in (.5,.95,.99,1.)}

def wrap(x):return (x+np.pi)%(2*np.pi)-np.pi
def yaw(m):return math.atan2(m[0][1],m[0][0])
def pose(y):
    m=np.eye(4);c,s=math.cos(y),math.sin(y);m[:2,:2]=[[c,s],[-s,c]];return m
def difference(a,b):
    a,b=np.asarray(a),np.asarray(b);r=a[:3,:3]@b[:3,:3].T
    return float(np.linalg.norm(a[3,:3]-b[3,:3])),float(abs(math.atan2(np.linalg.norm([r[2,1]-r[1,2],r[0,2]-r[2,0],r[1,0]-r[0,1]])/2,(np.trace(r)-1)/2)))

def ranges(directions,matrix):
    # Slab exit from an origin strictly inside the asymmetric box.
    m=np.asarray(matrix);v=directions@m[:3,:3];origin=m[3,:3]
    if np.any(origin<=BOUNDS[:,0]) or np.any(origin>=BOUNDS[:,1]):raise ValueError('origin outside qualified room')
    limits=np.where(v>0,BOUNDS[:,1],BOUNDS[:,0]);t=np.full_like(v,np.inf,dtype=float)
    np.divide(limits-origin,v,out=t,where=np.abs(v)>1e-12)
    t[t<=0]=np.inf
    return t.min(axis=1)

def geometry(points,matrix):
    m=np.asarray(matrix);world=np.asarray(points,dtype=float)@m[:3,:3]+m[3,:3]
    # Order differs from legacy oracle intentionally; selection remains nearest fixed plane.
    axes=np.array([0,0,1,1,2,2]);limits=BOUNDS.reshape(-1)
    d=np.abs(world[:,axes]-limits);order=np.argsort(d,axis=1,kind='stable');nearest=order[:,0]
    residual=d[np.arange(len(d)),nearest];keep=(d[np.arange(len(d)),order[:,1]]-residual>=.05)&(axes[nearest]<2)
    ids=nearest[keep];axis=axes[ids];v=world[keep]-m[3,:3];origin=m[3,:3]
    coverage={str(i):int(np.count_nonzero(ids==i)) for i in range(4)}
    enough=len(v)>=100 and any(coverage[str(i)]>=32 for i in (0,1)) and any(coverage[str(i)]>=32 for i in (2,3))
    delta=0.;information=None;reason=None
    if enough:
        for _ in range(4):
            c,s=math.cos(delta),math.sin(delta);x=c*v[:,0]-s*v[:,1];y=s*v[:,0]+c*v[:,1]
            j=np.where(axis==0,-y,x);information=float(j@j)
            if information<1:reason='insufficient_yaw_information';break
            e=np.where(axis==0,x+origin[0],y+origin[1])-limits[ids];delta-=float(j@e)/information
        if abs(delta)>math.radians(.2):reason='outside_fixed_yaw_measurement_range'
    else:reason='insufficient_fixed_wall_coverage'
    return {'point_plane_m':quantiles(residual),'yaw_error_rad':delta if reason is None else None,
        'fit_reason':reason,'fit_points':len(v),'wall_counts':coverage,'sum_J2_m2':information}

def decode(raw):
    if len(raw)<264:raise ValueError('GMO header short')
    magic,major,minor,patch,size,count=struct.unpack_from('<IIIIQI',raw)
    if magic!=0x4e474d4f or (major,minor,patch)!=(1,0,0) or not 264<=size<=len(raw):raise ValueError('GMO ABI/version/size not qualified')
    reference,comp=struct.unpack_from('<HH',raw,28);frame,stamp,coordinates,output=struct.unpack_from('<QQII',raw,32)
    model=np.array(struct.unpack_from('<16f',raw,56)).reshape(4,4)
    if coordinates not in (0,1) or reference not in (0,1) or not np.array_equal(model,np.eye(4)):raise ValueError('Unqualified coordinate/reference/model transform')
    header={'native_frame_id':str(frame),'timestamp_ns':str(stamp),'num_elements':count,'motion_compensation_code':comp,'coordinates_type_code':coordinates,'frame_of_reference_code':reference,
        'declared_packet_bytes':size,'owned_buffer_bytes':len(raw),'allocation_tail_bytes':len(raw)-size,'model_to_app_transform':model.tolist()}
    for name,offset in [('frame_start',120),('frame_end',160)]:
        header[name]={'timestamp_ns':str(struct.unpack_from('<Q',raw,offset)[0]),'quaternion_raw':list(struct.unpack_from('<4f',raw,offset+8)),'position_m':list(struct.unpack_from('<3f',raw,offset+24))}
    cursor=264;arrays={}
    def field(name,dtype,n):
        nonlocal cursor
        length=np.dtype(dtype).itemsize*n
        if cursor+length>size:raise ValueError('GMO serialized field exceeds declared span')
        arrays[name]=np.frombuffer(raw,dtype,count=n,offset=cursor).copy();cursor+=length
    for name,dtype in [('time_offset_ns','<i4'),('x','<f4'),('y','<f4'),('z','<f4'),('scalar','<f4'),('flags','u1')]:field(name,dtype,count)
    cursor=(cursor+7)//8*8;aux,modality=struct.unpack_from('<II',raw,200)
    if not aux or modality!=1 or cursor+88>size:raise ValueError('Lidar auxiliary identities unavailable')
    scan,az,mask=struct.unpack_from('<IfI',raw,cursor);cursor+=88;header.update(scan_complete=scan,azimuth_offset_deg=az,filled_members=mask)
    for bit,name,dtype,n in [(0,'emitter_id','<u4',1),(1,'channel_id','<u4',1),(3,'material_id','<u4',1),(5,'tick_id','<u4',1),(7,'hit_normals','<f4',3),(8,'velocities','<f4',3),(4,'object_id','u1',16),(2,'echo_id','u1',1),(6,'tick_states','u1',1)]:
        if mask&(1<<bit):field(name,dtype,count*n)
    if cursor!=size:raise ValueError('serialized length mismatch')
    return header,arrays,np.column_stack([arrays[k] for k in ('x','y','z')])

def classify(directions,observed,states,step):
    if any(k not in states for k in (step,step-1,step-2)):return {'status':'incomplete','best_members':[]}
    now=states[step];prev=states[step-1];half=np.asarray(now).copy();half[:3,:3]=pose(yaw(prev)+wrap(yaw(now)-yaw(prev))/2)[:3,:3]
    candidates={'current':now,'half':half,'previous1':prev,'previous2':states[step-2]};groups=[]
    for name,m in sorted(candidates.items()):
        group=next((g for g in groups if all(difference(m,candidates[n])[0]<=1e-8 and difference(m,candidates[n])[1]<=1e-8 for n in g)),None)
        if group is None:groups.append([name])
        else:group.append(name)
    values={n:quantiles(abs(ranges(directions,m)-observed))['0.95'] for n,m in candidates.items()}
    ranked=sorted(groups,key=lambda g:max(values[n] for n in g));best=ranked[0];v=max(values[n] for n in best)
    if len(ranked)==1:status='unobservable'
    else:
        second=min(min(values[n] for n in g) for g in ranked[1:])
        status='distinguishable' if v<=1e-5 and second>=10*v and second-v>=2e-5 else 'ambiguous'
    return {'status':status,'best_members':best,'groups':groups,'candidate_p95_m':values,'position_delay':'unknown: pure rotation','rotation_delay':'unknown' if len(ranked)==1 else status}
