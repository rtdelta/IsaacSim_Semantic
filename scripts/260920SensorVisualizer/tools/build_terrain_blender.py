"""Run with Blender's bundled Python; uses no addons, textures or downloads."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import bpy


def smoothstep(x):
    x=max(0.,min(1.,x))
    return x*x*(3-2*x)


def build(config_path, output):
    cfg=json.loads(Path(config_path).read_text())
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    for name in ('terrain.blend','terrain.usdc'):
        if (out/name).exists():raise FileExistsError('Refusing to replace '+str(out/name))
    rng=random.Random(cfg['seed'])
    waves=[(rng.uniform(.018,.055),rng.uniform(.3,1.1),rng.uniform(.3,1.1),rng.uniform(0,6.28)) for _ in range(8)]
    bumps=[(8,3,3.5,.45),(-8,-5,3.1,-.43),(2,-10,2.7,.36),(-7,8,3.2,.4),(10,-8,3,-.32)]
    sx,sy=cfg['size_m'];step=cfg['grid_step_m']
    nx,ny=round(sx/step),round(sy/step)
    if min(nx,ny)<2 or max(nx,ny)>1000:raise ValueError('Unsupported terrain grid size')
    vertices=[];heights=[]
    for j in range(ny+1):
        y=-sy/2+j*sy/ny
        for i in range(nx+1):
            x=-sx/2+i*sx/nx
            h=sum(a*math.sin(fx*x+fy*y+phase) for a,fx,fy,phase in waves)
            h+=sum(a*math.exp(-((x-bx)**2+(y-by)**2)/(2*s*s)) for bx,by,s,a in bumps)
            ellipse=math.hypot(x/cfg['startup_flat_ellipse_radii_m'][0],y/cfg['startup_flat_ellipse_radii_m'][1])
            h*=smoothstep((ellipse-1.)/.8)
            h*=smoothstep(min(sx/2-abs(x),sy/2-abs(y))/3.)
            vertices.append([x,y,h]);heights.append(h)
    factor=cfg['peak_to_valley_m']/(max(heights)-min(heights))
    for v in vertices:v[2]*=factor
    faces=[]
    for j in range(ny):
        for i in range(nx):
            a=j*(nx+1)+i;b=a+1;c=a+nx+1;d=c+1
            faces.extend([(a,b,d),(a,d,c)])
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    mesh=bpy.data.meshes.new('TerrainMesh');mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new('TerrainMesh',mesh);bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active=obj;obj.select_set(True)
    for i in range(24):
        value=.65+.7*i/23
        mat=bpy.data.materials.new(f'Earth_{i:02d}')
        if bpy.app.version < (5,0,0):mat.use_nodes=True
        color=(.28*value,.21*value,.115*value,1.)
        mat.diffuse_color=color
        bsdf=mat.node_tree.nodes.get('Principled BSDF')
        bsdf.inputs['Base Color'].default_value=color;bsdf.inputs['Roughness'].default_value=.9
        mesh.materials.append(mat)
    for face in mesh.polygons:
        v=vertices[face.vertices[0]]
        shade=.5+.22*math.sin(v[0]*2.7)*math.cos(v[1]*3.1)+.18*math.sin(v[0]*.6+v[1]*.9)
        face.material_index=max(0,min(23,int(shade*24)))
        face.use_smooth=True
    scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.
    scene['terrain_config_json']=json.dumps(cfg,sort_keys=True)
    obj['generated_by']='260920SensorVisualizer/build_terrain_blender.py'
    obj['terrain_seed']=cfg['seed']
    # Store a useful solid viewport without importing lights/cameras into USD.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.shading.color_type='MATERIAL'
                area.spaces.active.region_3d.view_distance=35
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'terrain.blend'))
    bpy.ops.wm.usd_export(filepath=str(out/'terrain.usdc'),selected_objects_only=True,
                          export_animation=False,export_materials=True,
                          root_prim_path='/Terrain')
    report={'config':cfg,'blender_version':bpy.app.version_string,'vertices':len(vertices),
            'triangles':len(faces),'min_height_m':min(v[2] for v in vertices),
            'max_height_m':max(v[2] for v in vertices),'external_downloads':[],
            'sha256':{n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ('terrain.blend','terrain.usdc')}}
    (out/'terrain_config.json').write_text(json.dumps(cfg,indent=2)+'\n')
    (out/'build_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('TERRAIN_RESULT='+json.dumps(report),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    build(args.config,args.output)
