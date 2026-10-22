"""Experimental same-process scene/product reuse between completed episodes.

Each episode retains the original native-clock/pose checks and new writer.
Only a fully finished episode can hand the paused scene to the next episode.
"""
import hashlib,json

class SceneLease:
    def __init__(self):self.scene=None;self.initialized=False;self.restore=[];self.key=None
    def bind(self,diag,job=None):
        scene=self.scene;scene.diag=diag
        if job:scene.job=job
        if scene.drivers:
            scene.drivers.diag=diag;scene.drivers.gate.diag=diag
    def install(self):
        from sensor_visualizer_v06 import replay_capture as replay
        from sensor_visualizer_v06.scene import SceneStepper
        owner=self;self.original_close=SceneStepper.close
        initialize=SceneStepper.initialize
        def factory(project,job,diag):
            key=json.dumps({k:job[k] for k in ('scene','render','physics_hz','capture')},sort_keys=True)
            if owner.scene is None:
                owner.key=key;owner.scene=SceneStepper(project,job,diag)
            else:
                if key!=owner.key:raise ValueError('Persistent scene contract changed between episodes')
                owner.scene.check_stage()
                if owner.scene.drivers.inflight is not None or owner.scene.drivers.generation_open:
                    raise RuntimeError('Previous render generation not drained')
                if owner.scene.drivers.ticket and owner.scene.drivers.ticket.open:raise RuntimeError('Previous ticket open')
                owner.bind(diag,job)
            return owner.scene
        async def reuse_initialize(scene,*args,**kwargs):
            if not owner.initialized:
                await initialize(scene,*args,**kwargs);owner.initialized=True
            else:
                scene.phase('initializing');scene.diag.event('lab_scene_reused',critical=True,
                    generation=scene.generation,resource_count=len(scene.drivers.products),
                    evidence='same live scene/products; prior generation drained; new native epoch per episode')
        async def retain_close(scene):
            if not owner.initialized or scene.invalid:return await owner.original_close(scene)
            scene.drivers.set_capture_active(False);scene.diag.event('lab_scene_retained',critical=True,
                generation=scene.generation,observation='paused; no generation or open ticket permitted on reuse')
        for cls,name,old,new in ((replay,'SceneStepper',replay.SceneStepper,factory),
                                  (SceneStepper,'initialize',initialize,reuse_initialize),
                                  (SceneStepper,'close',self.original_close,retain_close)):
            setattr(cls,name,new);self.restore.append((cls,name,old))
    async def final_close(self,diag):
        if self.scene and not self.scene.closed:
            self.bind(diag);await self.original_close(self.scene)
    def uninstall(self):
        for cls,name,fn in reversed(self.restore):setattr(cls,name,fn)
        self.restore=[]
