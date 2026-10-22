"""Save owned native bytes BEFORE any timing validation or ledger lookup."""
import hashlib,time
import numpy as np
from tools.clock_state.common import safe_value


def fetch(data,name):
    values=[v for k,v in data.items() if k==name or k.startswith(name+'-')]
    if len(values)!=1:raise ValueError('Expected one same-event '+name)
    return values[0]


def capture(data,native_writer,sequence,sink,context):
    row=dict(context,diagnostic_event_id='%s:%d'%(context['source_epoch'],sequence),receipt_seq=sequence,
        sensor_id=native_writer.entry['sensor_id'],kind=native_writer.kind,product_path=native_writer.product_path,
        received_monotonic_ns=str(time.monotonic_ns()),keys=list(data),copy_errors=[],ownership='owned_cpu',
        source_frame_id=None,native_event=None,payload_path=None)
    for name in ('ReferenceTime','IsaacReadSimulationTime'):
        try:row[name]=safe_value(fetch(data,name))
        except Exception as exc:row['copy_errors'].append(name+': '+str(exc))
    # Independent branches: a malformed header must not destroy a valid XYZ payload.
    try:
        cloud=fetch(data,'IsaacExtractRTXSensorPointCloud');array=cloud['data']
        array=array.numpy() if hasattr(array,'numpy') else array
        if not isinstance(array,np.ndarray) or array.dtype.kind!='f' or array.size%3:raise ValueError('Unexpected XYZ layout')
        if array.nbytes>64*1024**2:raise ValueError('XYZ byte bound')
        owned=np.array(array.reshape(-1,3),dtype='<f4',order='C',copy=True)
        if not np.isfinite(owned).all():raise ValueError('Nonfinite XYZ; no filtering')
        row.update(shape=list(owned.shape),dtype='<f4',raw_nbytes=owned.nbytes,points=len(owned),
            payload_sha256=hashlib.sha256(owned.tobytes()).hexdigest(),producer_shape=list(array.shape))
        row['payload_path']=sink.payload('payloads/lidar_%06d.xyz'%sequence,owned)
    except RuntimeError:raise  # Bounded storage failure is fatal, never silently dropped.
    except Exception as exc:row['copy_errors'].append('XYZ: '+str(exc))
    try:
        transform=np.asarray(fetch(data,'IsaacExtractRTXSensorPointCloud')['info']['transform'],dtype=float).reshape(4,4)
        if not np.isfinite(transform).all():raise ValueError('Nonfinite native transform')
        row['rendered_to_world']=transform.tolist()
    except Exception as exc:row['copy_errors'].append('native_pose: '+str(exc))
    try:
        packet=fetch(data,'GenericModelOutput');packet=packet['data'] if isinstance(packet,dict) else packet
        packet=packet.numpy() if hasattr(packet,'numpy') else packet
        if not isinstance(packet,np.ndarray) or packet.dtype!=np.uint8:raise ValueError('Unbounded/non-byte GMO')
        if not 264<=packet.nbytes<=64*1024**2:raise ValueError('GMO byte bound')
        owned=np.array(packet,dtype=np.uint8,order='C',copy=True).reshape(-1)
        metadata={'packet_path':sink.payload('trace_samples/gmo_%06d.bin'%sequence,owned),
            'packet_sha256':hashlib.sha256(owned.tobytes()).hexdigest(),'packet_nbytes':owned.nbytes,
            'ownership':'owned_cpu','provenance':'same Writer event original bytes; independent packed-header decode'}
        row['native_event']=metadata
        try:
            from single0601_continuous_rt.native_header import decode_header
            metadata.update(decode_header(owned.tobytes(),full_packet=True))
        except Exception as exc:
            metadata['decode_error']=str(exc);row['copy_errors'].append('GMO_decode: '+str(exc))
    except RuntimeError:raise
    except Exception as exc:row['copy_errors'].append('GMO: '+str(exc))
    row['copy_completed_monotonic_ns']=str(time.monotonic_ns())
    sink.event('raw_receipts.jsonl',row)
    return row


def associate(row,mapper,ledger):
    """Mapping errors are data, and cannot erase a previously saved event."""
    result=dict(row,rejection_reasons=[],clock_mapping_ok=None,physical_step=None,target_index=None,
        source_time_provenance={'annotator':'IsaacReadSimulationTime','scope':'same Writer event',
            'mapping_method':'get_simulation_time_at_time(ReferenceTime)',
            'mapping_independence':'Both values may share ExternalSimulationTime in multitick mode; not independent geometric truth'})
    source=mapped=None
    try:
        source=float(row['IsaacReadSimulationTime']['simulationTime'])
        if not np.isfinite(source):raise ValueError('Nonfinite source time')
        result.update(source_time_s=source,source_time_ns=str(round(source*1e9)))
    except Exception as exc:
        source=None;result['rejection_reasons'].append('source_time: '+str(exc))
    try:
        ref=row['ReferenceTime'];n=int(ref['referenceTimeNumerator']);d=int(ref['referenceTimeDenominator'])
        if d<=0:raise ValueError('Non-positive denominator')
        result['native_ref']={'kind':'rational_time','scope':row['product_path'],'numerator':str(n),'denominator':str(d),'event_id':None}
        mapped=float(mapper((n,d)))
        if not np.isfinite(mapped):raise ValueError('Nonfinite mapped time')
        result['mapped_time_ns']=str(round(mapped*1e9))
    except Exception as exc:
        mapped=None;result['rejection_reasons'].append('reference_mapping: '+str(exc))
    if source is not None and mapped is not None:
        result['reference_delta_ns']=round(mapped*1e9)-round(source*1e9)
        result['clock_mapping_ok']=abs(result['reference_delta_ns'])<=2
        if not result['clock_mapping_ok']:result['rejection_reasons'].append('source_reference_conflict')
    candidates={}
    for domain,stamp in [('source',result.get('source_time_ns')),('reference',result.get('mapped_time_ns'))]:
        if stamp is None:continue
        try:
            step,state=ledger.exact_time(row['source_epoch'],int(stamp));candidates[domain]={'physical_step':step,'actual_state':state}
        except Exception as exc:result['rejection_reasons'].append(domain+'_ledger: '+str(exc))
    result['association_candidates']=candidates
    if result['clock_mapping_ok'] is True and 'source' in candidates and 'reference' in candidates and candidates['source']['physical_step']==candidates['reference']['physical_step']:
        match=candidates['source'];result.update(physical_step=match['physical_step'],actual_state=match['actual_state'])
    result['formal_event_rejected']=bool(result['copy_errors'] or result['rejection_reasons'] or result['physical_step'] is None)
    return result
