"""Launch the offline packer in installed system ROS, never in Kit Python."""
import asyncio
import json
from pathlib import Path
import subprocess
import time
from .recording import ros_command, ros_environment


async def export_session(runtime, session):
    session=Path(session)
    if not (session/'capture_index.jsonl').is_file():return None
    if (session/'unified_export_report.json').is_file():
        report=json.loads((session/'unified_export_report.json').read_text())
        if report.get('state')=='complete' and Path(report['output']).is_dir():return Path(report['output'])
    runtime.exporting=True
    start=time.monotonic()
    runtime.performance.event('packing_started',session=str(session))
    try:
        with (session/'unified_export.log').open('ab') as log:
            process=subprocess.Popen(ros_command(runtime.config,['/usr/bin/python3',str(runtime.project_dir/'tools/pack_session_mcap.py'),str(session)]),
                env=ros_environment(runtime.config),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            runtime.performance.track('packer',process)
            while process.poll() is None:
                status={}
                try:status=json.loads((session/'unified_export_status.json').read_text())
                except (OSError,ValueError):pass
                runtime.set_status(f"Unified MCAP: {status.get('state','starting')} | Groups {status.get('groups',0)}/{status.get('total_groups','?')}")
                await asyncio.sleep(.5)
            if process.returncode:raise RuntimeError(f'Unified MCAP failed. Original files retained. See {session}/unified_export.log')
        return session/'bag_unified'
    finally:
        runtime.performance.track('packer',None)
        runtime.performance.event('span',name='recording.pack_and_verify',duration_s=time.monotonic()-start)
        runtime.exporting=False
