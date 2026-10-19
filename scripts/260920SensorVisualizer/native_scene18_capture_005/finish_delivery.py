"""Wait for the owned capture, export verified groups, and revalidate delivery."""
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path


def main(base):
    root = Path(__file__).resolve().parent
    base = Path(base)
    source = base/'production/capture'
    destination = base/'delivery_300'
    status_path = base/'delivery_status.json'
    status = {'state': 'waiting_for_capture', 'started_utc_ns': time.time_ns(),
              'source': str(source), 'destination': str(destination),
              'exporter_sha256': hashlib.sha256((root/'tools/export_groups.py').read_bytes()).hexdigest()}

    def write():
        temporary = status_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(status, indent=2))
        temporary.replace(status_path)

    write()
    try:
        deadline = time.monotonic() + 10800
        while True:
            result = source/'result.json'
            if result.exists():
                capture = json.loads(result.read_text())
                if capture['state'] != 'running':
                    break
            if time.monotonic() > deadline:
                raise TimeoutError('Capture result did not finish before deadline')
            time.sleep(10)
        assert capture['state'] == 'completed', 'Source capture failed; no delivery was exported'
        for script, args, phase in (
            ('export_groups.py', [str(source), str(destination)], 'exporting'),
            ('validate_bag.py', [str(destination)], 'validating_bag'),
            ('validate_groups.py', [str(destination)], 'validating_groups'),
        ):
            status['state'] = phase
            write()
            command = ['bash', '-c', 'source /opt/ros/jazzy/setup.bash && exec "$@"',
                       'native-delivery', '/usr/bin/python3', str(root/'tools'/script), *args]
            with (base/(phase+'.log')).open('xb') as log:
                result = subprocess.run(command, stdout=log, stderr=log, stdin=subprocess.DEVNULL, timeout=1800)
            if result.returncode:
                raise RuntimeError(phase+' failed; see '+str(base/(phase+'.log')))
        status['state'] = 'hashing'
        write()
        files = []
        for file in sorted((destination/'bag').iterdir()):
            if not file.is_file():
                continue
            digest = hashlib.sha256()
            with file.open('rb') as stream:
                for block in iter(lambda: stream.read(8*1024**2), b''):
                    digest.update(block)
            files.append({'path': str(file.relative_to(destination)), 'bytes': file.stat().st_size,
                          'sha256': digest.hexdigest()})
        (destination/'files_sha256.json').write_text(json.dumps(files, indent=2))
        selection = json.loads((destination/'selection_manifest.json').read_text())
        status.update(state='completed', completed_utc_ns=time.time_ns(), groups=selection['groups'],
                      messages=selection['messages'], files=files)
        write()
    except BaseException as exc:
        status.update(state='failed', error=type(exc).__name__+': '+str(exc))
        write()
        raise


if __name__ == '__main__':
    main(sys.argv[1])
