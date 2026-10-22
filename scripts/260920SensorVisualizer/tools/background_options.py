"""Retain the original backgrounds as independently editable scene nodes."""
import json
from pxr import Sdf, UsdGeom

BACKGROUND_NODES = {
    'original_textured_plane': '/FlatGrid/Environment/Geometry',
    'original_collision_plane': '/FlatGrid/GroundPlane/CollisionPlane',
    'original_3dgs_ground': '/environment_Fangshan_02/changjing4',
    'original_environment_texture': '/environment_Fangshan_02/DomeLight',
    'undulating_ground': '/World/UndulatingGround',
}


def restore_background_options(stage):
    """Author only the caller's edit layer; keep geometry/material arcs intact."""
    for name in ('original_textured_plane', 'original_collision_plane'):
        prim = stage.GetPrimAtPath(BACKGROUND_NODES[name])
        if not prim:
            raise ValueError('Missing original ground: '+BACKGROUND_NODES[name])
        UsdGeom.Imageable(prim).CreateVisibilityAttr().Set(UsdGeom.Tokens.inherited)
    # Remove the terrain-only collision override, restoring the source asset's setting.
    stage.GetPrimAtPath(BACKGROUND_NODES['original_collision_plane']).RemoveProperty('physics:collisionEnabled')
    prim = stage.GetPrimAtPath(BACKGROUND_NODES['original_3dgs_ground'])
    if not prim:
        raise ValueError('Missing original 3DGS background')
    prim.SetActive(True)
    # This can also run with standalone USD before the NVIDIA GS schema is loaded.
    prim.CreateAttribute('visibility', Sdf.ValueTypeNames.Token, custom=False).Set('inherited')
    layer = stage.GetRootLayer()
    data = dict(layer.customLayerData)
    info = dict(data.get('sensorVisualizerTerrain', {}))
    info.update(oldGroundHiddenJson='[]', backgroundPolicy='All original backgrounds retained; user controls visibility',
                backgroundNodesJson=json.dumps(BACKGROUND_NODES, sort_keys=True))
    data['sensorVisualizerTerrain'] = info
    layer.customLayerData = data
    return dict(BACKGROUND_NODES)
