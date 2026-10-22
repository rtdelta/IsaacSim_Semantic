"""Verify the executed sources, then package only the explicitly selected material."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'reports/remote/reports/issue_repro/minimal_20261016_v2'
PACKAGE = ROOT/'repro/instant_lidar_timing'
DOC = ROOT/'docs/Experiments/009_连续旋转时序问题_简要说明与最小复现_20261016.md'


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    status = json.loads((SOURCE/'status.json').read_text())
    assert status['state'] == 'complete' and status['remaining_kit_pids'] == []
    cases = ('static_on', 'rotate_on', 'static_off', 'rotate_off')
    included = []
    total_events = total_targets = 0
    for case in cases:
        src = SOURCE/case
        hashes = json.loads((src/'source_hashes.json').read_text())
        assert set(hashes) == {'capture.py', 'analyze.py', 'launch.py', 'sensor.json'}
        for name, expected in hashes.items():
            assert digest(PACKAGE/name) == expected == digest(src/'sources'/name), (case, name)
        summary = json.loads((src/'summary.json').read_text())
        assert all(summary[k] for k in ('measurement_qualified', 'capture_complete', 'cleanup_ok'))
        assert summary['targets'] == 20 and summary['native_events'] == 26
        process = json.loads((src/'process.json').read_text())
        assert process['exited'] and process['exit_code'] == 0 and not process['timed_out']
        rows = list(csv.DictReader((src/'samples.csv').open()))
        assert len(rows) == 20 and all(int(r['valid_returns']) == 10 for r in rows)
        for key in ('current', 'half', 'previous'):
            values = sorted(float(r[key+'_p95_m']) for r in rows)
            median = (values[9]+values[10])/2
            assert abs(median-summary['median_target_p95_m'][key]) < 1e-15
        events = json.loads((src/'events.json').read_text())
        for event in events:
            raw = gzip.decompress((src/event['path']).read_bytes())
            assert hashlib.sha256(raw).hexdigest() == event['sha256_uncompressed']
        names = ['summary.json', 'samples.csv', 'per_ray.csv', 'environment.json',
                 'source_hashes.json', 'physics.json', 'updates.json', 'plan.json',
                 'effective_sensor.json', 'settings.json', 'events.json', 'callback_errors.json']
        names += [e['path'] for e in events]
        dest = PACKAGE/'verified_results'/case
        dest.mkdir(parents=True, exist_ok=False)
        for name in names:
            shutil.copy2(src/name, dest/name)
            included.append((dest/name).relative_to(PACKAGE).as_posix())
        total_events += len(events)
        total_targets += len(rows)
    shutil.copy2(DOC, PACKAGE/'简要说明.md')
    top = ['launch.py', 'capture.py', 'analyze.py', 'sensor.json', 'README.md',
           'DISCUSSION_DRAFT.md', 'VERIFICATION.md', '简要说明.md']
    included += top
    # Review text selected for the portable package, excluding machine-specific launch/log files.
    forbidden = ['/root/', 'D:\\', 'D:/', 'CloudInstanceOps/', 'credential_ref', 'password=', 'token=']
    for name in included:
        p = PACKAGE/name
        if p.suffix in ('.json', '.md', '.csv', '.py'):
            text = p.read_text(encoding='utf-8')
            assert not any(s in text for s in forbidden), name
    locked = json.loads((ROOT/'config/native_rotation_localization/v1/main_code_lock.json').read_text())['files']
    assert all(digest(ROOT/f['path']) == f['sha256'] for f in locked)
    files = [{'path': name, 'bytes': (PACKAGE/name).stat().st_size, 'sha256': digest(PACKAGE/name)}
             for name in sorted(included)]
    manifest = {'date': '2026-10-16', 'validation_suite': 'minimal_20261016_v2',
                'validated_targets': total_targets, 'validated_native_events': total_events,
                'source_versions_match_all_four_executed_runs': True,
                'original_007_locked_files_unchanged': len(locked),
                'files': files, 'scope': 'Observation and semantics question; no confirmed SDK defect.'}
    (PACKAGE/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    archive = ROOT/'repro/instant_lidar_timing_20261016.zip'
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(included + ['manifest.json']):
            z.write(PACKAGE/name, 'instant_lidar_timing/'+name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert len(z.infolist()) == len(files)+1
        for f in files:
            assert hashlib.sha256(z.read('instant_lidar_timing/'+f['path'])).hexdigest() == f['sha256']
    receipt = {'archive': str(archive.relative_to(ROOT)), 'bytes': archive.stat().st_size,
               'sha256': digest(archive), 'files': len(files)+1,
               'target_scans': total_targets, 'native_payloads': total_events,
               'source_versions_match': True, 'original_locked_files_unchanged': len(locked)}
    (ROOT/'reports/issue_repro_package_20261016.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
