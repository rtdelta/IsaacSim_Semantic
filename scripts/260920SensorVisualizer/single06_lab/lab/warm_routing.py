"""Experimental warm routing; retain 16 camera subframes and frozen native clock.

Prime every sensor before selectively warming cameras. Correctness gates remain
unchanged; SDK-stale pose/time rejects this candidate instead of saving bad data.
"""
class WarmRouting:
    def __init__(self):self.original=None
    def install(self):
        from sensor_visualizer_v06.sensors import SensorDrivers
        self.original=SensorDrivers.warm_cameras
        async def warm(driver,subframes,retain_generation=False):
            if getattr(driver,'backend',None)!='persistent_gated':raise ValueError('Warm routing requires persistent writer backend')
            driver.gate.all(True,'lab_all_sensor_pose_prime')
            complete=False
            try:
                await driver._step(1,'lab_all_sensor_pose_prime')
                driver.set_lidar_updates(False,'lab_camera_only_warmup')
                await driver._step(subframes,'lab_camera_only_warmup')
                driver.gate.all(True,'lab_formal_all_sensor_prepare')
                driver.diag.event('lab_warm_routing',critical=True,camera_subframes=subframes,
                    all_sensor_prime_subframes=1,native_clock_advance=0,
                    evidence='all sensors start generation at frozen pose; original formal time/pose/receipt checks retained')
                complete=True
            finally:
                if not complete:driver.gate.all(False,'lab_warmup_failed')
        SensorDrivers.warm_cameras=warm
    def uninstall(self):
        from sensor_visualizer_v06.sensors import SensorDrivers
        if self.original:SensorDrivers.warm_cameras=self.original
