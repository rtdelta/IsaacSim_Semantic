"""Temporarily retire persisted LiDAR products while this tool owns their output."""
class RenderLease:
    def __init__(self, stage, layer, sensor_paths):
        self.nodes, self.products = [], []
        from pxr import Usd, UsdRender
        sensors = set(sensor_paths)
        with Usd.EditContext(stage, layer):
            for prim in list(stage.Traverse()):
                node_type = prim.GetAttribute('node:type')
                if node_type and node_type.Get() == 'isaacsim.core.nodes.IsaacCreateRenderProduct':
                    cameras = prim.GetRelationship('inputs:cameraPrim').GetTargets()
                    if cameras and str(cameras[0]) in sensors:
                        prim.GetAttribute('inputs:enabled').Set(False)
                        self.nodes.append(str(prim.GetPath()))
                if prim.IsA(UsdRender.Product):
                    cameras = UsdRender.Product(prim).GetCameraRel().GetTargets()
                    # Persisted scene products only; never commandeer another
                    # tool's anonymous/session render product.
                    authored_on_disk = any(not spec.layer.anonymous for spec in prim.GetPrimStack())
                    if authored_on_disk and cameras and str(cameras[0]) in sensors:
                        self.products.append(str(prim.GetPath()))
            for prim in list(stage.Traverse()):
                if prim.IsA(UsdRender.Settings):
                    rel = UsdRender.Settings(prim).GetProductsRel()
                    targets = rel.GetTargets()
                    if any(str(t) in self.products for t in targets):
                        rel.SetTargets([t for t in targets if str(t) not in self.products])
            for path in self.products:
                stage.OverridePrim(path).SetActive(False)

    def metadata(self):
        return {'suspended_initializer_nodes': self.nodes, 'suspended_scene_products': self.products,
                'restoration': 'Removing the runtime session layer restores all opinions'}
