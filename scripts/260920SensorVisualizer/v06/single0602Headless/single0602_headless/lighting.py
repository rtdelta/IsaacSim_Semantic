"""Explicit DomeLight selection in the removable runtime layer."""
def select_dome(stage,layer,selected_path,backend,diagnostics):
    from pxr import Usd,UsdGeom
    domes=[p for p in stage.Traverse() if p.GetTypeName()=='DomeLight']
    visible=[p for p in domes if UsdGeom.Imageable(p).ComputeVisibility()!=UsdGeom.Tokens.invisible]
    before=[{'path':str(p.GetPath()),'visibility':str(UsdGeom.Imageable(p).ComputeVisibility()),
             'intensity':p.GetAttribute('inputs:intensity').Get(),
             'texture':str(p.GetAttribute('inputs:texture:file').Get())} for p in domes]
    if selected_path is None:
        if backend=='persistent_gated' and len(visible)>1:
            raise ValueError('Multiple visible DomeLights: select a visible target render.background_dome')
        return {'policy':'preserve_authored','before':before,'disabled':[]}
    selected=stage.GetPrimAtPath(selected_path)
    if not selected or selected.GetTypeName()!='DomeLight':
        raise ValueError('Configured render.background_dome is missing: '+selected_path)
    if UsdGeom.Imageable(selected).ComputeVisibility()==UsdGeom.Tokens.invisible:
        raise ValueError('Selected DomeLight is hidden; choose a visible DomeLight')
    disabled=[]
    with Usd.EditContext(stage,layer):
        for prim in domes:
            if str(prim.GetPath())!=selected_path:
                disabled.append(str(prim.GetPath()));prim.SetActive(False)
    result={'policy':'explicit_single_dome','selected':selected_path,'before':before,'disabled':disabled,
            'scope':'removable runtime Session layer; original USD never saved',
            'reason':'Native tests found competing DomeLights select different camera backgrounds across capture lifecycles'}
    diagnostics.event('dome_light_selection',critical=True,**result)
    return result
