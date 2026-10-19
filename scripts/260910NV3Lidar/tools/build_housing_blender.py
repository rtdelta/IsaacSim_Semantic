"""Build a simple NZ3 housing with Blender; export only geometry/materials to USDA.

Run with Blender --background --factory-startup --python this.py -- --output DIR.
Dimensions are from the supplied NZ3 specification. The silhouette, panel layout
and optical-origin-to-housing alignment are explicitly approximate.
"""
import argparse
import json
import math
from pathlib import Path
import sys

import bpy
import bmesh
from mathutils import Vector


def material(name, color, roughness, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    return mat


def finish(obj, mat):
    obj.data.materials.append(mat)
    bpy.context.view_layer.objects.active = obj
    for p in obj.data.polygons:
        p.use_smooth = True
    normal = obj.modifiers.new('Weighted_corner_normals', 'WEIGHTED_NORMAL')
    normal.keep_sharp = True
    bpy.ops.object.modifier_apply(modifier=normal.name)
    return obj


def rounded_box(name, dims, loc, bevel, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel > 0:
        mod = obj.modifiers.new('Rounded_edges', 'BEVEL')
        mod.width = bevel
        mod.segments = 5
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return finish(obj, mat)


def panel(name, width, height, radius, thickness, loc, side, mat):
    # Rounded rectangle extruded in its normal direction. Unlike a bevelled thin
    # cube, this retains millimetre-scale corner radii with sub-mm thickness.
    outline = []
    for cx, cy, start in ((width/2-radius, height/2-radius, 0),
                          (-width/2+radius, height/2-radius, 90),
                          (-width/2+radius, -height/2+radius, 180),
                          (width/2-radius, -height/2+radius, 270)):
        for j in range(7):
            a = math.radians(start+j*90/6)
            outline.append((cx+radius*math.cos(a), cy+radius*math.sin(a)))
    vertices = []
    for w in (-thickness/2, thickness/2):
        for u, v in outline:
            if side == 'top': point = (u, v, w)
            elif side == 'front': point = (w, u, v)
            elif side == 'back': point = (-w, -u, v)
            elif side == 'left': point = (-u, w, v)
            else: point = (u, -w, v)
            vertices.append(tuple(point[k]+loc[k] for k in range(3)))
    n = len(outline)
    faces = [tuple(reversed(range(n))), tuple(range(n, 2*n))]
    faces += [(i, (i+1)%n, (i+1)%n+n, i+n) for i in range(n)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    bm = bmesh.new(); bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(mesh); bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return finish(obj, mat)


def aim(obj, target=(0, 0, 0)):
    obj.rotation_euler = (Vector(target)-obj.location).to_track_quat('-Z', 'Y').to_euler()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    args.output.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'; scene.unit_settings.scale_length = 1
    body = material('Housing_satin_black', (.010, .013, .017), .38, .02)
    window = material('Window_dark_gloss', (.022, .030, .038), .19, .08)
    lid = material('Top_graphite', (.019, .022, .027), .38, .03)
    base = material('Base_black', (.010, .013, .017), .44, .12)
    rear = material('Rear_panel', (.022, .026, .031), .48)
    pieces = [
        rounded_box('Body', (.085, .070, .092), (0, 0, .001), .010, body),
        panel('Base', .086, .071, .010, .005, (0, 0, -.0475), 'top', base),
        panel('Top_cap', .083, .068, .012, .007, (0, 0, .0465), 'top', lid),
        panel('Front_window', .044, .070, .006, .0008, (.0426, 0, .001), 'front', window),
        panel('Left_window', .047, .070, .006, .0008, (.001, .0351, .001), 'left', window),
        panel('Right_window', .047, .070, .006, .0008, (.001, -.0351, .001), 'right', window),
        panel('Rear_cover', .045, .068, .004, .0008, (-.0426, 0, 0), 'back', rear),
    ]
    bpy.context.view_layer.update()
    coords = [o.matrix_world @ v.co for o in pieces for v in o.data.vertices]
    lower = [min(v[k] for v in coords) for k in range(3)]
    upper = [max(v[k] for v in coords) for k in range(3)]
    dims = [upper[k]-lower[k] for k in range(3)]
    assert all(abs(a-b)<1e-6 for a,b in zip(dims, [.086,.071,.100])), dims
    radius = max(v.length for v in coords)
    # 5mm margin; round up to the next 5mm. This is distance-based, not a mesh-ID mask.
    offset = math.ceil((radius+.005)/.005)*.005
    assert offset < .2
    tris = 0
    for o in pieces:
        o.data.calc_loop_triangles(); tris += len(o.data.loop_triangles)
        bm = bmesh.new(); bm.from_mesh(o.data)
        assert all(e.is_manifold for e in bm.edges), o.name
        bm.free()
    metadata = dict(version='1.2',blender_version=bpy.app.version_string,
        dimensions_xyz_m=dims,dimensions_whd_mm=[71,100,86],bounds_min_m=lower,
        bounds_max_m=upper,max_vertex_radius_m=radius,range_offset_m=offset,
        near_range_m=.2,mesh_count=len(pieces),triangle_count=tris,
        origin='Optical origin approximated at housing bounding-box centre; not mechanically calibrated',
        axes='+X forward, +Y left, +Z up',mesh_names=[o.name for o in pieces],
        scope='Simple visual housing; approximate silhouette/panels, no rigid body or collider',
        source='NZ3&5_Specification V4.0_20260521.pdf: cover appearance and page 2 overall dimensions')
    (args.output/'housing_manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
    bpy.ops.object.select_all(action='DESELECT')
    for o in pieces: o.select_set(True)
    bpy.context.view_layer.objects.active = pieces[0]
    bpy.ops.wm.usd_export(filepath=str(args.output/'NZ3_housing.usda'),
        selected_objects_only=True,export_animation=False,export_materials=True,
        generate_preview_surface=True,generate_materialx_network=False,
        export_normals=True,export_uvmaps=False,export_meshes=True,
        export_lights=False,export_cameras=False,convert_world_material=False,
        root_prim_path='/Housing',relative_paths=True,convert_orientation=False,
        convert_scene_units='METERS',author_blender_name=False)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output/'NZ3_housing.blend'))
    # Inspection render only. Studio objects are added after export/source save.
    ground = material('Studio_ground', (.19,.21,.24), .75)
    rounded_box('Studio_floor', (200,200,.002), (0,0,-.0515), 0, ground)
    scene.world.color = (.32,.32,.32)
    for name,loc,power,size in [('Key',(.13,.16,.22),.9,.18),
                               ('Fill',(.15,-.20,.08),.5,.14),
                               ('Rim',(-.13,.02,.22),1.2,.12)]:
        data=bpy.data.lights.new(name,'AREA');data.energy=power;data.shape='DISK';data.size=size
        obj=bpy.data.objects.new(name,data);scene.collection.objects.link(obj);obj.location=loc;aim(obj)
    cam=bpy.data.objects.new('PreviewCamera',bpy.data.cameras.new('PreviewCamera'))
    scene.collection.objects.link(cam);scene.camera=cam;cam.data.type='ORTHO';cam.data.ortho_scale=.165
    scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=32
    scene.render.resolution_x=900;scene.render.resolution_y=900;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX'
    for name,pos in [('perspective',(.22,.19,.13)),('rear',(-.22,-.17,.11))]:
        cam.location=pos;aim(cam,(0,0,-.002));scene.render.filepath=str(args.output/f'{name}.png')
        bpy.ops.render.render(write_still=True)
    print('NZ3_HOUSING_BUILT',json.dumps(metadata),flush=True)


if __name__=='__main__':main()
