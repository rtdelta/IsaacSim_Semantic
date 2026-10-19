"""Optional cross-thread NVTX ranges via the already installed native library."""
import ctypes
import ctypes.util
import sys

class NativeTrace:
    def __init__(self):
        names=[ctypes.util.find_library('nvToolsExt')]
        if sys.platform.startswith('linux'):names+=['/usr/local/cuda/lib64/libnvToolsExt.so.1']
        last=None
        for name in filter(None,names):
            try:self.api=ctypes.CDLL(name);break
            except OSError as exc:last=exc
        else:raise RuntimeError('Existing NVTX library unavailable') from last
        self.api.nvtxRangeStartA.argtypes=[ctypes.c_char_p]
        self.api.nvtxRangeStartA.restype=ctypes.c_uint64
        self.api.nvtxRangeEnd.argtypes=[ctypes.c_uint64]
    def begin(self,label):return int(self.api.nvtxRangeStartA(label.encode('utf-8')[:1024]))
    def end(self,zone):self.api.nvtxRangeEnd(zone)
