"""Flatten DAE scene transforms without modifying vertices, materials or upstream files.

The bundled converter accumulates local @ parent, while these column-vector
COLLADA matrices require parent @ local. A single scene-node depth avoids that
version-specific importer error without patching the installed application.
"""
import copy
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import numpy as np

ROOT = Path('/root/gpufree-data/IsaacSim_Asset/excavator_module_set/CET200')
source = ROOT / 'source/cet200_description'
target = ROOT / 'prepared/cet200_description'
assert not target.exists()
shutil.copytree(source, target)
URI = 'http://www.collada.org/2005/11/COLLADASchema'
NS = {'c': URI}
ET.register_namespace('', URI)
report = {'reason': 'Single-level DAE node transforms avoid reversed nested-matrix accumulation in the bundled converter.', 'files': []}
for path in sorted((target/'meshes').glob('*.dae')):
    tree = ET.parse(path)
    changed = 0
    for scene in tree.getroot().findall('c:library_visual_scenes/c:visual_scene', NS):
        nodes = []
        def walk(node, parent):
            nonlocal_unused = None
            transforms = [x for x in node if x.tag.split('}')[-1] in ('matrix','translate','rotate','scale','lookat','skew')]
            assert all(x.tag == '{'+URI+'}matrix' for x in transforms), path
            local = np.eye(4)
            for transform in transforms:
                local = local @ np.array(list(map(float, transform.text.split()))).reshape(4,4)
            world = parent @ local
            instances = node.findall('c:instance_geometry', NS)
            if instances:
                flat = ET.Element('{'+URI+'}node', {'id': 'flat_'+str(len(nodes)), 'name': node.get('name',node.get('id','part')), 'type':'NODE'})
                matrix = ET.SubElement(flat, '{'+URI+'}matrix', {'sid':'transform'})
                matrix.text = ' '.join(format(float(x), '.17g') for x in world.flat)
                for inst in instances:
                    flat.append(copy.deepcopy(inst))
                nodes.append(flat)
            assert not node.findall('c:instance_node', NS), 'Instanced COLLADA nodes require explicit resolution'
            for child in node.findall('c:node', NS):
                walk(child, world)
        for node in scene.findall('c:node', NS):
            walk(node, np.eye(4))
        for node in list(scene):
            scene.remove(node)
        scene.extend(nodes)
        changed += len(nodes)
    tree.write(path, encoding='utf-8', xml_declaration=True)
    report['files'].append({'file': str(path.relative_to(ROOT)), 'geometry_instances': changed})
(ROOT/'reports/dae_compatibility.json').write_text(json.dumps(report, indent=2))
archive=ROOT/'reports/initial_import'
archive.mkdir()
for name in ('CET200.usda',):
    p=ROOT/'usd'/name
    if p.exists(): p.rename(archive/name)
for name in ('build_report.json','build_cet200.log','build_cet200_kit.log'):
    p=ROOT/'reports'/name
    if p.exists(): p.rename(archive/name)
print(json.dumps(report, indent=2))
