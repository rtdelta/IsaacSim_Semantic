"""Bounded group-boundary cooperation; does not preempt RTX work or drop samples."""
import asyncio,time
from .control_ipc import request

def yield_duration_ms(config,owner,now_ns):
    delay=config['cooperative_yield_ms']
    if not config['yield_only_with_owner']:return delay
    age=now_ns-owner.get('heartbeat_ns',0) if owner else -1
    return delay if owner and owner.get('phase')=='interactive_ready' and 0<=age<=3_000_000_000 else 0

async def group_boundary_yield(config,socket_path,diagnostics,group):
    if not config['cooperative_yield_ms']:return
    owner=None
    if config['yield_only_with_owner']:
        try:owner=await asyncio.to_thread(request,socket_path,{'action':'snapshot'},.2)
        except (OSError,EOFError,ValueError):return
    delay=yield_duration_ms(config,owner,time.monotonic_ns())
    if delay:
        with diagnostics.span('cooperative_group_yield',group_id=group,requested_ms=delay,
                              scheduling_scope='task boundary; no GPU preemption'):
            await asyncio.sleep(delay/1000)
