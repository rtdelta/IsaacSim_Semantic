import shutil,json
from pathlib import Path
print(json.dumps({'installed':{n:shutil.which(n) for n in ('gdb','perf','nsys','py-spy','strace')},'perf_event_paranoid':Path('/proc/sys/kernel/perf_event_paranoid').read_text().strip()}))
