"""Compute lens FOV and a flat-ground, no-occlusion coverage illustration."""
import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
evidence = PROJECT / 'reports/surround_fisheye'
data = json.loads((HERE / 'composed_verified.json').read_text())
cal = json.loads((evidence / 'sample_metadata/front/calibration.json').read_text())
intr = cal['intrinsics']
k = np.array([intr['k' + str(i)] for i in range(1, 5)])

def distort(theta):
    return theta * (1 + sum(a * theta ** (2 * i + 2) for i, a in enumerate(k)))

def invert(r):
    lo, hi = 0.0, math.pi / 2
    for _ in range(80):
        middle = (lo + hi) / 2
        if distort(middle) < r:
            lo = middle
        else:
            hi = middle
    return (lo + hi) / 2

angles = {
    'left': invert(intr['cx'] / intr['fx']),
    'right': invert((cal['width'] - 1 - intr['cx']) / intr['fx']),
    'up': invert(intr['cy'] / intr['fy']),
    'down': invert((cal['height'] - 1 - intr['cy']) / intr['fy']),
}
assert np.all(np.diff(distort(np.linspace(0, math.pi / 2, 1000))) > 0)
fov = {name: math.degrees(value) for name, value in angles.items()}
fov['horizontal'] = fov['left'] + fov['right']
fov['vertical'] = fov['up'] + fov['down']

x = np.linspace(-12, 8, 601)
y = np.linspace(-8, 12, 601)
xx, yy = np.meshgrid(x, y)
points = np.stack([xx, yy, np.zeros_like(xx)], axis=-1)
coverage = np.zeros(xx.shape, dtype=np.uint8)
rows = []
for cam in data['camera_world']:
    cid = cam['id']
    m = np.array(cam['usd_to_world'])
    rotation = m[:3, :3] * np.array([1, -1, -1])[:, None]
    assert np.allclose(rotation @ rotation.T, np.eye(3), atol=1e-7)
    position = m[3, :3]
    local = (points - position) @ rotation.T
    radius = np.linalg.norm(local[..., :2], axis=-1)
    theta = np.arctan2(radius, local[..., 2])
    factor = distort(np.minimum(theta, math.pi / 2)) / np.maximum(radius, 1e-12)
    u = intr['fx'] * local[..., 0] * factor + intr['cx']
    v = intr['fy'] * local[..., 1] * factor + intr['cy']
    visible = ((local[..., 2] > 0) & (u >= 0) & (u <= cal['width'] - 1)
               & (v >= 0) & (v <= cal['height'] - 1))
    coverage += visible.astype(np.uint8)
    forward = rotation[2]
    lower_ray = np.array([0, math.sin(angles['down']), math.cos(angles['down'])]) @ rotation
    ground_hit = position + (-position[2] / lower_ray[2]) * lower_ray
    snap = json.loads(data['snapshot'][cid + '/frame.json']['text'])
    local_image_sha = hashlib.sha256((evidence / (cid + '.png')).read_bytes()).hexdigest()
    image_match = local_image_sha == data['recording_first_images'][cid]['sha256']
    assert image_match
    rows.append({'id': cid, 'world_position_m': position.tolist(),
                 'yaw_world_deg': math.degrees(math.atan2(forward[1], forward[0])),
                 'downward_world_deg': math.degrees(math.asin(-forward[2])),
                 'initial_snapshot_matrix_max_error': float(np.max(np.abs(m - np.array(snap['camera_usd_to_world'])))),
                 'recorded_image_sha_matches_remote': image_match,
                 'bottom_center_ray_distance_to_ground_z0_m': float(np.linalg.norm(ground_hit[:2] - position[:2]))})

fig, ax = plt.subplots(figsize=(9, 8))
colors = ['#f0f0f0', '#b9dcf5', '#51a6d7', '#2474ab', '#104467']
im = ax.pcolormesh(xx, yy, coverage, cmap=ListedColormap(colors),
                   norm=BoundaryNorm(np.arange(-0.5, 5.5), 5), shading='auto', rasterized=True)
for row, cam in zip(rows, data['camera_world']):
    px, py, _ = row['world_position_m']
    m = np.array(cam['usd_to_world'])
    dx, dy = -m[2, :2]
    ax.arrow(px, py, dx * 1.1, dy * 1.1, width=.055, head_width=.32, color='#d75b24')
    ax.plot(px, py, 'o', color='#292929', markersize=5)
    ax.annotate(row['id'], (px, py), xytext=(7, 7), textcoords='offset points', weight='bold')
ax.set(xlabel='World X (m)', ylabel='World Y (m)', aspect='equal',
       title='Four fisheye cameras: ideal flat-ground coverage\nCurrent saved pose; ground Z=0; NO body/terrain occlusion')
ax.grid(alpha=.15)
fig.colorbar(im, ax=ax, ticks=range(5), label='Number of cameras whose field of view contains the point')
fig.text(.08, .02, 'Grey = outside all modelled fields of view. Coloured areas may still be blocked by geometry.', fontsize=9)
fig.tight_layout(rect=(0, .04, 1, 1))
fig.savefig(HERE / 'ideal_ground_coverage.png', dpi=160)
plt.close(fig)
result = {'source': 'Current disk USD composition plus separately verified Sep 21 recording evidence',
          'model': 'OpenCV fisheye, front hemisphere, alpha=0',
          'fov_center_cross_sections_deg': fov, 'cameras': rows,
          'ground_plot_limits': 'Ideal world Z=0 plane only; no raycasting, no body, boom, terrain or Gaussian visibility test',
          'new_render_performed': False}
(HERE / 'coverage_analysis.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
