"""Analyze captured point buffers; no simulation or source USD edits."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parent
evidence = root / 'evidence'
selected = ['gs_off_multi_rgb', 'gs_on_multi_rgb', 'gs_hidden_on', 'gs_inactive_on',
            'mesh_moving_on', 'gs_mask_string0', 'gs_mask_string1',
            'full_original_bvh_v3', 'full_mesh_bvh_v3', 'full_source_mesh_bvh_v4']
analysis = {}
for name in selected:
    directory = evidence / 'cases' / name
    path = directory / 'result.json'
    if not path.exists():
        path = directory / 'progress.json'
    if not path.exists():
        continue
    result = json.loads(path.read_text())
    process = json.loads((directory / 'process.json').read_text())
    rows = result.get('samples', [])
    arrays = [np.load(p)['xyz'] for p in sorted(directory.glob('sample_*.npz'))]
    points = np.concatenate(arrays) if arrays else np.empty((0, 3))
    log = (directory / 'console.log').read_text(errors='replace')
    analysis[name] = {
        'status': result['status'], 'buffers': len(rows),
        'process': process,
        'complete_buffers': sum(bool(r['scan_complete']) for r in rows),
        'counts': sorted(set(r['count'] for r in rows)),
        'gaussian_error_count': log.count('Gaussians do not support motion BVH'),
        'motion_disabled_warning_count': log.count('MotionBVH for lidar model not enabled'),
        'saved_points': len(points),
        'saved_near_hits_lt8m': int((np.linalg.norm(points, axis=1) < 8).sum()),
        'geometry': result.get('geometry', {}).get('type_counts'),
        'isolation': result.get('mesh_isolation'),
        'effective_settings': result.get('effective_settings'),
    }
    if len(points) and name in ['gs_on_multi_rgb', 'gs_hidden_on', 'gs_inactive_on']:
        analysis[name]['static_chamber_max_surface_error_m'] = float(
            np.min(np.abs(np.abs(points) - 10), axis=1).max())

(root / 'analysis.json').write_text(json.dumps(analysis, indent=2))
plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), constrained_layout=True)
for ax, name, title in zip(axes, ['gs_off_multi_rgb', 'gs_on_multi_rgb'],
                           ['Motion BVH OFF: Gaussian returns present', 'Motion BVH ON: Gaussian returns disappear']):
    directory = evidence / 'cases' / name
    samples = sorted(directory.glob('sample_0_*.npz'))
    points = np.concatenate([np.load(p)['xyz'] for p in samples])
    near = np.linalg.norm(points, axis=1) < 8
    ax.scatter(points[~near, 0], points[~near, 1], s=5, color='#70869a', alpha=.25, label='Mesh chamber')
    ax.scatter(points[near, 0], points[near, 1], s=17, color='#df572e', alpha=.7,
               label=f'Near returns (<8 m): {near.sum()}')
    ax.scatter([0], [0], marker='*', s=95, color='#167886', label='Lidar')
    ax.set(xlim=(-11, 11), ylim=(-11, 11), xlabel='Sensor x (m)', ylabel='Sensor y (m)', title=title)
    ax.set_aspect('equal')
    ax.grid(alpha=.15)
    ax.legend(loc='lower left', fontsize=8)
fig.suptitle('Same static Gaussian asset + same mesh chamber | RTX Lidar | Isaac Sim 6.0.1-rc.7', fontsize=12)
fig.savefig(root / 'gaussian_motion_bvh_comparison.png', dpi=180)
print(json.dumps(analysis, indent=2))
