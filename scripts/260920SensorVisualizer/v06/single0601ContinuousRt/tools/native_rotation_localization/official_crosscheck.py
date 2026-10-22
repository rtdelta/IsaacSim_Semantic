"""After capture only: installed parser cross-check on bounded owned bytes."""
import gzip,hashlib
import numpy as np
from .io import rows
from .math_independent import decode

def check(directory):
    from isaacsim.sensors.experimental.rtx import parse_generic_model_output_data
    results=[]
    paths={r['native_event']['packet_path'] for r in rows(directory/'raw_events.jsonl') if r.get('native_event')}
    paths.update(r['packet_path'] for r in rows(directory/'api_polls.jsonl') if r.get('packet_path'))
    for path in sorted(paths):
        row={'path':path}
        try:
            raw=gzip.decompress((directory/path).read_bytes());h,a,xyz=decode(raw)
            owned=np.frombuffer(raw,dtype=np.uint8).copy();g=parse_generic_model_output_data(owned)
            official=np.column_stack((np.asarray(g.x),np.asarray(g.y),np.asarray(g.z)))
            fields=[('flags','flags'),('emitter_id','emitterId'),('channel_id','channelId'),('tick_id','tickId'),('echo_id','echoId')]
            same=np.array_equal(official,xyz) and all(np.array_equal(a[k],np.asarray(getattr(g,n))) for k,n in fields if k in a)
            row.update(passed=bool(same and int(g.frameId)==int(h['native_frame_id']) and int(g.timestampNs)==int(h['timestamp_ns'])),
                sha256=hashlib.sha256(raw).hexdigest(),num_elements=int(g.numElements))
        except Exception as exc:row.update(passed=False,error=str(exc))
        results.append(row)
    return {'passed':bool(results) and all(r['passed'] for r in results),'decoded_files':len(results),'files':results,
        'timing':'after fixed capture end, cleanup and sink close; never in progression callbacks'}
