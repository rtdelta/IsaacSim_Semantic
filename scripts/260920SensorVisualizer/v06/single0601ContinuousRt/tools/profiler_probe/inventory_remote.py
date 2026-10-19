"""Read installed archive metadata and relevant process mappings only."""
import json, re, subprocess
from pathlib import Path
install=Path('/root/isaacsim')
archives=[]
for base in ('exts','extscache','extsDeprecated'):
    directory=install/base
    if not directory.is_dir():
        continue
    for pattern in ('*/pip_prebundle/torch/version.py','*/pip_prebundle/torch/profiler/__init__.py',
                    '*/pip_archive/torch/version.py','*/pip_archive/torch/profiler/__init__.py'):
        for path in directory.glob(pattern):
            row={'path':str(path),'bytes':path.stat().st_size}
            if path.name=='version.py':
                row['versions']=[line for line in path.read_text(errors='replace').splitlines()
                                 if re.match(r'^(?:__version__|cuda|hip|debug)\s*[:=]',line)]
            ext=path.parents[2] if path.name=='version.py' else path.parents[3]
            config=ext/'config/extension.toml'
            if config.exists():
                lines=config.read_text(errors='replace').splitlines()
                row['extension_metadata_lines']=[s for s in lines if any(k in s for k in ('version =','version=','name =','name=','pip_prebundle','torch','title ='))][:30]
            archives.append(row)
processes=[]
for p in Path('/proc').iterdir():
    if not p.name.isdigit(): continue
    try:
        raw=(p/'cmdline').read_bytes()
        if b'/kit/kit' not in raw: continue
        arguments=raw.decode(errors='replace').split('\0')
        entries=[Path(arguments[i+1]).name for i,t in enumerate(arguments[:-1]) if t=='--exec']
        maps=(p/'maps').read_text(errors='replace').splitlines()
        libraries=sorted({line.split()[-1] for line in maps if any(s in line.lower() for s in ('libtorch','libcupti','libkineto'))})
        processes.append({'pid':int(p.name),'entry_basenames':entries,'profiler_related_libraries':libraries})
    except OSError: pass
system=subprocess.run(['/usr/bin/python3','-I','-B','-c',
                      "import importlib.util,json,sys; p=importlib.util.find_spec('torch'); print(json.dumps({'python':sys.version.split()[0],'torch':p.origin if p else None}))"],
                      capture_output=True,text=True,timeout=15)
print(json.dumps({'installed_archives':archives,'live_kit_processes':processes,'system_python':system.stdout.strip()}))
