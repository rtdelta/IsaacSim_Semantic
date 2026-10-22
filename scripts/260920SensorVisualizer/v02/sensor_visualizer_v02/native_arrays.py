"""Copy RTX auxiliary buffers using the pointer's actual CUDA memory type."""
import ctypes
import numpy as np

_driver=None

def copy_float_pointer(pointer,count):
    global _driver
    if count==0: return np.empty(0,dtype=np.float32),{'memory':'empty'}
    if pointer<=0 or count<0 or count>100_000_000: raise ValueError('Invalid native float buffer')
    if _driver is None:
        _driver=ctypes.CDLL('libcuda.so.1')
        _driver.cuPointerGetAttribute.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_uint64]
        _driver.cuPointerGetAttribute.restype=ctypes.c_int
    memory=ctypes.c_uint()
    status=_driver.cuPointerGetAttribute(ctypes.byref(memory),2,pointer)
    if status==0 and memory.value in (2,4):
        device=ctypes.c_int()
        if _driver.cuPointerGetAttribute(ctypes.byref(device),9,pointer): raise RuntimeError('Cannot resolve CUDA pointer device')
        import warp as wp
        with wp.ScopedDevice('cuda:'+str(device.value)):
            array=wp.array(ptr=pointer,dtype=wp.float32,shape=(count,),device='cuda:'+str(device.value),copy=False)
            return array.numpy(),{'memory':'cuda','device':device.value}
    # Do not dereference an unmapped or GPU-only host address, even if the
    # extractor incorrectly labels its common cudaDeviceIndex as -1.
    readable=False
    with open('/proc/self/maps') as stream:
        for line in stream:
            parts=line.split(); start,end=(int(x,16) for x in parts[0].split('-'))
            if parts[1].startswith('r') and start<=pointer and pointer+count*4<=end:
                readable=True; break
    if not readable: raise RuntimeError(f'Native pointer is neither readable host memory nor recognized CUDA memory (CUDA {status})')
    view=np.ctypeslib.as_array((ctypes.c_float*count).from_address(pointer))
    return view.copy(),{'memory':'cpu','cuda_query_status':status}
