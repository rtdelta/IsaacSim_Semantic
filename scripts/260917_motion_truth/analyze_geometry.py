import json
from pathlib import Path
root = Path(__file__).resolve().parent
import numpy as np
import trimesh
meta = json.loads((root/'geometry/geometry.json').read_text())
meshes = {}
for row in meta['meshes']:
    if row['group'] != 'source_mesh':
        continue
    data = np.load(root/'geometry'/row['file'])
    link = row['path'].split('/Visuals/')[0]
    meshes[link] = trimesh.Trimesh(vertices=data['vertices'], faces=data['faces'], process=False)
rows = []
for field in meta['gaussians']:
    link = field['path'].split('/Visuals/')[0]
    data = np.load(root/'geometry'/field['file'])
    mask = data['opacities'] >= .5
    points = data['positions'][mask]
    values = []
    for start in range(0, len(points), 512):
        _, distances, _ = trimesh.proximity.closest_point(meshes[link], points[start:start+512])
        values.extend(distances)
    d = np.asarray(values)
    item = {'part': field['name'], 'gs_path': field['path'], 'mesh_link': link,
            'sampled_all_opacities': field['sampled'], 'used_opacity_ge_0_5': len(points),
            'median_m': float(np.median(d)), 'p95_m': float(np.quantile(d, .95)),
            'p99_m': float(np.quantile(d, .99)), 'max_m': float(d.max()),
            'fraction_within_1cm': float((d <= .01).mean()),
            'fraction_within_5cm': float((d <= .05).mean())}
    rows.append(item)
    np.savez_compressed(root/'geometry'/('distances_'+field['name']+'.npz'), points=points, distances=d)
    print(json.dumps(item), flush=True)
out = {'method': 'Unfitted world-space high-opacity Gaussian-center to corresponding link triangle surface distance. '
                 'This is a registration diagnostic, not a physical LiDAR depth accuracy metric.',
       'seed': 20260917, 'parts': rows,
       'visible_reference_meshes': [m['path'] for m in meta['meshes'] if m['group'] != 'source_mesh' and m['visible']]}
(root/'geometry_analysis.json').write_text(json.dumps(out, indent=2))
