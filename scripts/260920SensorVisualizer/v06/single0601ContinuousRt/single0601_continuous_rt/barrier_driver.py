"""One native manual Writer request at an exact physical boundary, no per-group warmup."""
import asyncio
import time
from .common import ContractError,source_ns
from .sensor_backend import BarrierBackend


class BarrierDriver:
    def __init__(self,owner):
        self.owner=owner

    async def prepare(self):
        import omni.replicator.core as rep
        o=self.owner
        o.timeline.play()
        o.timeline.commit()
        for _ in range(o.job['render']['initial_warmup_min_updates']):
            await o.app.next_update_async()
        o.timeline.pause()
        o.timeline.commit()
        rep.orchestrator.set_capture_on_play(False)
        o.backend.__class__=BarrierBackend
        o.backend.use_manual_triggers()
        o.backend.permit=lambda ns:False

    async def target(self,step,complete,deadline_ns):
        o=self.owner
        if o.manager.get_num_physics_steps()>=step:
            raise ContractError('late_reservation','Target must be reserved before physics reaches it')
        o.backend.permit=lambda ns:False
        o.timeline.play()
        o.timeline.commit()
        while o.manager.get_num_physics_steps()<step:
            await o.app.next_update_async()
            if o.error:
                raise ContractError(o.error['code'],o.error['message'])
        if o.manager.get_num_physics_steps()!=step:
            raise ContractError('skipped_physical_step','Barrier physical target was skipped')
        o.timeline.pause()
        o.timeline.commit()
        actual_ns=source_ns(o.manager.get_simulation_time())
        o.backend.permit=lambda ns:abs(ns-actual_ns)<=2
        o.backend.schedule()
        await asyncio.wait_for(o.backend.render_once(),o.job['capture']['group_timeout_wall_s'])
        while not complete():
            if time.monotonic_ns()>deadline_ns:
                raise ContractError('missing_sensor','Manual native completion missed its target deadline')
            await o.app.next_update_async()
            if o.error:
                raise ContractError(o.error['code'],o.error['message'])
        o.backend.permit=lambda ns:False
