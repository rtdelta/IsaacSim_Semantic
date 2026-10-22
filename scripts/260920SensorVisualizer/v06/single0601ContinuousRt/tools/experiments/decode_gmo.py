"""Independent serialized v1 GMO arrays. Never dereference native pointers.

Layout follows installed GenericModelOutput.h getBaseGMOPtrFromBuffer and
GMOAuxiliaryData.h cpyLidAuxToBuffer; recorded header SHA is kept as evidence.
"""
import struct
import numpy as np
from single0601_continuous_rt.native_header import decode_header


def decode(raw):
    header=decode_header(raw,full_packet=True);count=header['num_elements'];offset=264;arrays={}
    def array(name,dtype,n):
        nonlocal offset
        size=np.dtype(dtype).itemsize*n
        if offset+size>len(raw):raise ValueError('Serialized GMO array exceeds owned bytes')
        arrays[name]=np.frombuffer(raw,dtype=dtype,count=n,offset=offset).copy();offset+=size
    for name,dtype in [('time_offset_ns','<i4'),('x','<f4'),('y','<f4'),('z','<f4'),('scalar','<f4'),('flags','u1')]:array(name,dtype,count)
    offset=(offset+7)//8*8
    auxiliary={}
    if header['aux_type_code'] and header['modality_code']==1:
        if offset+88>len(raw):raise ValueError('Truncated LidarAuxiliaryData')
        scan,azimuth,filled=struct.unpack_from('<IfI',raw,offset);offset+=88
        auxiliary={'scan_complete':scan,'azimuth_offset_deg':azimuth,'filled_members':filled}
        for bit,name,dtype,mult in [(0,'emitter_id','<u4',1),(1,'channel_id','<u4',1),(3,'material_id','<u4',1),
            (5,'tick_id','<u4',1),(7,'hit_normals','<f4',3),(8,'velocities','<f4',3),(4,'object_id','u1',16),(2,'echo_id','u1',1),(6,'tick_states','u1',1)]:
            if filled & (1<<bit):array(name,dtype,count*mult)
    if offset!=header['declared_packet_bytes']:raise ValueError('Serialized GMO size differs from declared ABI layout')
    xyz=np.column_stack([arrays['x'],arrays['y'],arrays['z']])
    if header['coordinates_type_code']==1:
        azimuth=np.deg2rad(xyz[:,0].astype(float));elevation=np.deg2rad(xyz[:,1].astype(float));distance=xyz[:,2]
        xyz=np.column_stack([distance*np.cos(elevation)*np.cos(azimuth),distance*np.cos(elevation)*np.sin(azimuth),distance*np.sin(elevation)])
    elif header['coordinates_type_code']!=0:raise ValueError('Unsupported point coordinate type')
    return header,arrays,auxiliary,xyz
