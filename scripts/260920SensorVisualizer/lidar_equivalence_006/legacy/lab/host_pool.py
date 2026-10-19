"""Optional session-owned CPU buffers. SDK arrays are never retained.

Reuse is permitted only after submit's shielded pack/send has completed. The
writer consumes an independent mmap copy. This cannot reduce SDK cudaHostAlloc.
"""
class HostPool:
    def __init__(self):self.buffers={};self.leases=set();self.restore=[];self.failed=False
    def install(self):
        from sensor_visualizer_v06.sensors import SensorDrivers,host
        from sensor_visualizer_v06.pipeline import RecordPipeline
        from sensor_visualizer_v06.scene import SceneStepper
        import numpy as np
        pool=self
        original_copy=SensorDrivers._copy_host;original_submit=RecordPipeline.submit;original_capture=SceneStepper.capture
        def copy_host(driver,value,sensor):
            if pool.failed:raise RuntimeError('Host pool poisoned by failed submit')
            with driver.diag.span('host_materialize',sensor_id=sensor,measurement_source='host elapsed may include GPU wait'):
                materialized=host(value)
            with driver.diag.span('cpu_owned_copy',sensor_id=sensor,bytes=int(materialized.nbytes),strategy='session_host_pool'):
                result=pool.buffers.get(sensor)
                reuse=result is not None and result.shape==materialized.shape and result.dtype==materialized.dtype
                if not reuse:result=np.empty_like(materialized);pool.buffers[sensor]=result
                result.flags.writeable=True;np.copyto(result,materialized);pool.leases.add(sensor)
            driver.diag.event('lab_host_pool_copy',sensor_id=sensor,reused=reuse,bytes=int(result.nbytes),
                release_signal='RecordPipeline.submit pack/send completed',sdk_buffer_retained=False)
            return result
        async def capture(scene,*args,**kwargs):
            if pool.leases:raise RuntimeError('Host buffers still leased by previous group')
            return await original_capture(scene,*args,**kwargs)
        async def submit(pipeline,*args,**kwargs):
            try:result=await original_submit(pipeline,*args,**kwargs)
            except BaseException:pool.failed=True;raise
            pool.leases.clear();pipeline.diag.event('lab_host_pool_released',critical=True,
                evidence='packing thread completed; record worker reads independent mmap slot')
            return result
        for cls,name,original,replacement in ((SensorDrivers,'_copy_host',original_copy,copy_host),
                                             (SceneStepper,'capture',original_capture,capture),
                                             (RecordPipeline,'submit',original_submit,submit)):
            setattr(cls,name,replacement);self.restore.append((cls,name,original))
    def uninstall(self):
        for cls,name,fn in reversed(self.restore):setattr(cls,name,fn)
        self.restore=[]
