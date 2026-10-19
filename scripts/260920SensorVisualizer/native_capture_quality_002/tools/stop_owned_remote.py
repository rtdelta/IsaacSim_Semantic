"""Stop only the Kit process recorded by this project's current failed smoke."""
import json,os,signal
from pathlib import Path
root=Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/native_capture_quality_002')
info=json.loads((root/'reports/latest_execution.json').read_text());out=Path(info['directory'])
assert out.resolve().is_relative_to(Path('/root/gpufree-data/semantic/output/native_capture_quality_002'))
r=json.loads((out/'result.json').read_text());pid=r['supervised_pid'];args=(Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')
if not args[0].endswith(b'/kit/kit') or str(root/'kit_entry.py').encode() not in args:raise RuntimeError('PID ownership mismatch')
(out/'stop.request').write_text('NC002 smoke transition timeout; stopped owned engine only')
os.killpg(pid,signal.SIGTERM);print(json.dumps({'stopped_owned_engine_pid':pid,'directory':str(out)}))
