from pathlib import Path
import json
import hashlib
root = Path('/root/gpufree-data/semantic/scripts/260920SensorVisualizer/v02')
report = json.loads((root/'reports/probe_capture.json').read_text())
rows = []
for row in report.get('samples', []):
    cloud = row['3_IsaacExtractRTXSensorPointCloud']
    rows.append({'index': row['index'], 'timeline': [row['timeline_before'], row['timeline_after']],
                 'native': [row.get('native_before'), row.get('native_after')],
                 'target_hits': row.get('known_target_hits'), 'face_error': row.get('target_face_max_error'),
                 'lidar_pose_error': row.get('lidar_render_pose_error'),
                 'camera_time': row['2_IsaacReadSimulationTime'], 'lidar_time': row['4_IsaacReadSimulationTime'],
                 'cloud': cloud['data'], 'transform': cloud.get('info', {}).get('transform'),
                 'camera_view': row['1_CameraParams']['cameraViewTransform'],
                 'cloud_sha256': hashlib.sha256((root/f"reports/probe_cloud_{row['index']}.npy").read_bytes()).hexdigest(),
                 'image_sha256': hashlib.sha256((root/f"reports/probe_{row['index']}.png").read_bytes()).hexdigest()})
print(json.dumps({'state': report['state'], 'samples': rows}))
raise SystemExit(0)
base = Path('/root/isaacsim')
patterns = [('exts/isaacsim.sensors.rtx.nodes', 'IsaacExtractRTXSensorPointCloud'),
            ('exts/isaacsim.core.nodes', 'IsaacReadSimulationTime'),
            ('exts/isaacsim.core.simulation_manager', 'def set_'),
            ('extscache', 'IsaacExtractRTXSensorPointCloud')]
matches = []
for folder, needle in patterns:
    directory = base/folder
    if folder == 'extscache':
        candidates = [p for d in directory.glob('omni.sensors.nv.common-*') for p in d.rglob('*.py')]
    else:
        candidates = list(directory.rglob('*.py'))+list(directory.rglob('*.ogn'))
    for p in candidates:
        if p.stat().st_size > 200000: continue
        lines = p.read_text(errors='replace').splitlines()
        indexes = [i for i, line in enumerate(lines) if needle in line]
        if indexes:
            ranges = sorted(set(j for i in indexes for j in range(max(0,i-3), min(len(lines),i+12))))
            matches.append({'path': str(p), 'lines': [{'n':i+1, 'text':lines[i]} for i in ranges[:120]]})
print(json.dumps({'sources': matches[:25]}))
