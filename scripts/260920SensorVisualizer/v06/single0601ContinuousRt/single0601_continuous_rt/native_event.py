"""CPU-owned native event evidence; never borrows a GMO object after callback."""
import hashlib
import numpy as np
from .common import ContractError
from .geometry import matrix_from_pose
from .native_header import decode_header


def frame_at_time(frame):
    q = [float(x) for x in frame.orientation]
    p = [float(x) for x in frame.posM]
    candidates = {}
    # Diagnostic alternatives only. Quaternion order must be established from
    # native declarations and non-symmetric geometry before formal adaptation.
    if len(q) == 4 and np.isfinite(q).all() and abs(np.dot(q,q)-1) < 1e-5:
        candidates['xyzw'] = matrix_from_pose(p,q).tolist()
        candidates['wxyz'] = matrix_from_pose(p,q[1:]+q[:1]).tolist()
    return {'timestamp_ns':str(int(frame.timestampNs)), 'position_m':p,
            'orientation_raw':q, 'quaternion_order':'not_yet_verified',
            'diagnostic_matrix_candidates':candidates}


class NativeEventAdapter:
    """Use the installed parser on bounded owned bytes, within Writer.write()."""
    def __init__(self, max_bytes=64*1024*1024):
        from isaacsim.sensors.experimental.rtx import parse_generic_model_output_data
        self.parse = parse_generic_model_output_data
        self.max_bytes = max_bytes

    def capture(self, packet):
        if isinstance(packet,dict):
            packet = packet['data']
        if hasattr(packet,'numpy'):
            packet = packet.numpy()
        if not isinstance(packet,np.ndarray):
            raise ContractError('gmo_pointer','Diagnostic adapter requires array data, not an unbounded pointer')
        raw = np.array(packet,dtype=np.uint8,order='C',copy=True).reshape(-1)
        if raw.nbytes < 264 or raw.nbytes > self.max_bytes:
            raise ContractError('gmo_size','Native GMO packet is outside the declared byte bound')
        header = raw.tobytes()
        decoded=decode_header(header,full_packet=True)
        # getModelOutputFromBuffer rebases pointer fields in its input buffer.
        # Parse another owned copy so the retained native packet stays original.
        parse_buffer=raw.copy()
        gmo = self.parse(parse_buffer)
        count = int(gmo.numElements)
        offsets = np.array(gmo.timeOffsetNs,dtype='<i4',copy=True)
        if len(offsets) != count:
            raise ContractError('gmo_offsets','Native point offsets do not match numElements')
        metadata = {'schema_version':1,'provenance':'same Writer event GenericModelOutput; installed SDK parser',
            'ownership':'owned_cpu','packet_nbytes':raw.nbytes,
            'packet_sha256':hashlib.sha256(header).hexdigest(),
            'parser_input_mutated':not np.array_equal(raw,parse_buffer),
            'structure_version':[int(gmo.majorVersion),int(gmo.minorVersion),int(gmo.patchVersion)],
            'native_frame_id':str(int(gmo.frameId)), 'timestamp_ns':str(int(gmo.timestampNs)),
            'clock_domain':'unverified native GMO clock; retained separately from physics time',
            'num_elements':count,'frame_of_reference':str(gmo.frameOfReference),
            'coordinates_type':str(gmo.elementsCoordsType),
            'motion_compensation_state':str(gmo.motionCompensationState),
            'model_to_app_transform_raw':np.array(gmo.modelToAppTransform,dtype=float,copy=True).tolist(),
            'frame_start':frame_at_time(gmo.frameStart),'frame_end':frame_at_time(gmo.frameEnd),
            'point_time_offsets':{'dtype':'<i4','count':count,
                'min_ns':str(int(offsets.min())) if count else None,
                'max_ns':str(int(offsets.max())) if count else None,
                'sha256':hashlib.sha256(offsets.tobytes()).hexdigest()}}
        for key in ('structure_version','native_frame_id','timestamp_ns','num_elements','model_to_app_transform_raw'):
            if decoded[key]!=metadata[key]:raise ContractError('gmo_parser','Installed parser disagrees with independently decoded native header: '+key)
        for point in ('frame_start','frame_end'):
            for key in ('timestamp_ns','orientation_raw','position_m'):
                if decoded[point][key]!=metadata[point][key]:raise ContractError('gmo_parser','Installed parser disagrees with independent frame pose')
        metadata['packed_header_independent_match']=True
        return metadata,raw
