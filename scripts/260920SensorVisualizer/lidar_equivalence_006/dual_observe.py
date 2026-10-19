"""CPU -> CUDA -> CPU observation with no intervening Kit update/render."""
import hashlib,json
from pathlib import Path
import numpy as np
def owned(v):
    v=v.numpy() if hasattr(v,'numpy') else np.asarray(v)
    return np.ascontiguousarray(v,dtype='<f4').reshape(-1,3).copy()
def digest(a):return hashlib.sha256(a.tobytes()).hexdigest()
def raw_snapshot(ann):
    from isaacsim.sensors.experimental.rtx import parse_generic_model_output_data
    raw=ann.get_data();raw=raw['data'] if isinstance(raw,dict) else raw
    if hasattr(raw,'numpy'):raw=raw.numpy()
    if not isinstance(raw,np.ndarray):raise TypeError('Raw pointer input refused; require owned ndarray')
    raw=np.ascontiguousarray(raw).copy();gmo=parse_generic_model_output_data(raw)
    if not 0<int(gmo.numElements)<10_000_000 or int(gmo.sizeInBytes)>raw.nbytes:raise ValueError('Invalid raw buffer header')
    meta={n:int(getattr(gmo,n)) for n in ('frameId','timestampNs','numElements','sizeInBytes')}
    meta.update(elementsCoordsType=str(gmo.elementsCoordsType),frameOfReference=str(gmo.frameOfReference),modality=str(gmo.modality),auxType=str(gmo.auxType))
    arrays={};errors={}
    for name in ('x','y','z','scalar','flags','emitterId','channelId','echoId','objectId','materialId','tickId','timeOffsetNs'):
        try:
            a=getattr(gmo,name)
            if isinstance(a,np.ndarray):arrays[name]=a.copy()
        except Exception as exc:errors[name]=type(exc).__name__+': '+str(exc)
    meta['array_shapes']={n:list(a.shape) for n,a in arrays.items()};meta['unavailable_fields']=errors
    meta['xyz_raw_sha256']={n:hashlib.sha256(arrays[n].tobytes()).hexdigest() for n in ('x','y','z') if n in arrays}
    return meta,arrays

def compare_exits(out,group,sid,cpu,gpu,first,stage,product,stamp,raw_ann,id_ann):
    import omni.timeline
    from isaacsim.core.simulation_manager import SimulationManager
    before=SimulationManager.get_simulation_time()
    raw_before,raw_arrays=raw_snapshot(raw_ann)
    dest=Path(out)/'dual_exit'/f'{group:03d}';dest.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(dest/(sid+'_raw.npz'),**raw_arrays)
    (dest/(sid+'_raw_header.json')).write_text(json.dumps(raw_before,indent=2))
    # SDK 1.13.27 clears its per-node cache on an empty auxiliary array and
    # can then KeyError when copying a later CUDA array. Request a borrowed
    # view, immediately own it, and restore the observer-only copy flag.
    flag=gpu.get_node().get_attribute('outputs:__do_array_copy')
    previous=flag.get() if flag.is_valid() else None
    try:
        if previous is not None:flag.set(False)
        got=gpu.get_data(device='cuda',do_array_copy=False);cuda=owned(got['data'])
    finally:
        if previous is not None:flag.set(previous)
    again=cpu.get_data(device='cpu');last=owned(again['data'])
    raw_after,_=raw_snapshot(raw_ann)
    after=SimulationManager.get_simulation_time()
    np.save(dest/(sid+'_cuda.npy'),cuda,allow_pickle=False)
    np.savez_compressed(dest/(sid+'_raw.npz'),**raw_arrays)
    idmap={}
    try:
        from isaacsim.sensors.experimental.rtx import parse_stable_id_map_data
        v=id_ann.get_data();v=v['data'] if isinstance(v,dict) else v
        if hasattr(v,'numpy'):v=v.numpy()
        if isinstance(v,np.ndarray) and v.size:idmap=parse_stable_id_map_data(v.copy())
    except Exception as exc:idmap={'error':str(exc)}
    if group==0:(dest/(sid+'_object_map.json')).write_text(json.dumps(idmap,indent=2))
    paths=[]
    for p in stage.Traverse():
        if Path(product).name not in str(p.GetPath()):continue
        a=p.GetAttribute('node:type')
        if a and ('ExtractRTXSensor' in str(a.Get()) or 'GenericModelOutput' in str(p.GetPath())):
            paths.append({'path':str(p.GetPath()),'type':str(a.Get()),'connections':{a.GetName():[str(x) for x in a.GetConnections()] for a in p.GetAttributes() if a.GetConnections()}})
    def metadata(d):
        result={}
        for k,v in d.items():
            result[k]={'type':type(v).__module__+'.'+type(v).__name__,'shape':list(getattr(v,'shape',())),'device':str(getattr(v,'device','not_exposed'))}
        return result
    row={'group':group,'sensor':sid,'render_product':product,'stamp_s':stamp,'simulation_before_s':before,'simulation_after_s':after,'kit_update_between_reads':False,'cpu_points':len(first),'cuda_points':len(cuda),'cpu_before_sha256':digest(first),'cuda_sha256':digest(cuda),'cpu_after_sha256':digest(last),'cpu_stable':np.array_equal(first,last),'cpu_cuda_identical':np.array_equal(first,cuda),'cuda_info':metadata(got.get('info',{})),'cpu_info':metadata(again.get('info',{})),'upstream_graph':paths,'limits':'No raw GMO frame counter or hit payload decoded; graph provenance and non-advancing back-to-back reads are evidence, not an invented emission ID.'}
    row.update(raw_before=raw_before,raw_after=raw_after,raw_stable=raw_before==raw_after,original_copy_flag=previous,copy_flag_restored=flag.get() if previous is not None else None,limits='Raw header and arrays parsed with installed SDK from an owned CPU buffer; no direct pointer dereference or synthesized emission identifier. Observer copy flag temporarily False for CUDA read only; no engine updates between reads.')
    (dest/(sid+'.json')).write_text(json.dumps(row,indent=2))
    if before!=after:raise RuntimeError('Time advanced during dual observation')
