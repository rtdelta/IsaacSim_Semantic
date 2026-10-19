"""Independent byte decoder for the installed packed GenericModelOutput v1 ABI.

Only values within the 264-byte header are decoded. Native pointer fields are
never dereferenced; all large integers retain their decimal-string form.
"""
import math
import struct
from .common import ContractError

HEADER_BYTES=264
SUPPORTED_VERSION=(1,0,0)


def decode_header(raw,full_packet=False):
    if len(raw)<HEADER_BYTES:raise ContractError('gmo_header','Truncated packed GMO header')
    magic,major,minor,patch,size,count=struct.unpack_from('<4I Q I',raw)
    if magic!=0x4E474D4F:raise ContractError('gmo_magic','Invalid GMO header magic')
    if (major,minor,patch)!=SUPPORTED_VERSION:
        raise ContractError('gmo_version','Unsupported GMO structure version')
    if size<HEADER_BYTES or (full_packet and size>len(raw)):
        raise ContractError('gmo_layout','Invalid GMO declared packet size')
    ref,comp=struct.unpack_from('<2H',raw,28)
    frame_id,timestamp,coords,output=struct.unpack_from('<2Q2I',raw,32)
    model=list(struct.unpack_from('<16f',raw,56))
    def frame(offset):
        stamp=struct.unpack_from('<Q',raw,offset)[0]
        values=struct.unpack_from('<7f',raw,offset+8)
        if not all(math.isfinite(x) for x in values):
            raise ContractError('gmo_pose','Nonfinite native frame pose')
        return {'timestamp_ns':str(stamp),'orientation_raw':list(values[:4]),'position_m':list(values[4:])}
    if not all(math.isfinite(x) for x in model):raise ContractError('gmo_pose','Nonfinite native model transform')
    return {'structure_version':[major,minor,patch],'declared_packet_bytes':size,'num_elements':count,
        'native_frame_id':str(frame_id),'timestamp_ns':str(timestamp),'frame_of_reference_code':ref,
        'motion_compensation_code':comp,'coordinates_type_code':coords,'output_type_code':output,
        'model_to_app_transform_raw':model,'frame_start':frame(120),'frame_end':frame(160),
        'aux_type_code':struct.unpack_from('<I',raw,200)[0],'modality_code':struct.unpack_from('<I',raw,204)[0]}
