"""An isolated RTX experiment. Source USD layers are never saved or edited."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import time
import traceback

p = argparse.ArgumentParser()
p.add_argument("--out", type=Path, required=True)
p.add_argument("--geometry", choices=["mesh", "gaussian", "full"], default="mesh")
p.add_argument("--source", default="/root/gpufree-data/IsaacSim_Asset/excavator_module_set/Sim_Fangshan_02/3dgs_usd/tooth_01_front.usd")
p.add_argument("--bvh", type=int, choices=[0, 1], default=0)
p.add_argument("--multi", type=int, choices=[0, 1], default=0)
p.add_argument("--gaussian-state", choices=["visible", "hidden", "inactive"], default="visible")
p.add_argument("--moving", choices=["none", "sensor", "gaussian"], default="none")
p.add_argument("--frames", type=int, default=120)
p.add_argument("--replays", type=int, default=1)
p.add_argument("--inspect-only", action="store_true")
p.add_argument("--engines", default="all", help="all disables masking, or comma-separated Hydra engine IDs")
p.add_argument("--capture", action="store_true")
p.add_argument("--exclude-gaussians", action="store_true")
a, _ = p.parse_known_args()
a.out = a.out.resolve()
a.out.mkdir(parents=True, exist_ok=True)
result = {"args": {k: str(v) if isinstance(v, Path) else v for k, v in vars(a).items()},
          "status": "starting", "phases": [], "samples": []}


def phase(name, **extra):
    result["phase"] = name
    result["phases"].append({"name": name, "wall_time": time.time(), **extra})
    (a.out / "progress.json").write_text(json.dumps(result, indent=2))
    print("BVH_PROBE", name, json.dumps(extra), flush=True)


phase("app_start")
from isaacsim import SimulationApp

flags = ["--/app/settings/loadUserConfig=false", "--/app/settings/persistent=false",
         "--/app/asyncRendering=false", "--/app/file/ignoreUnsavedOnExit=true",
         "--/app/player/useFixedTimeStepping=true", "--/app/player/useFastMode=false",
         "--/renderer/raytracingMotion/enabled=" + str(bool(a.bvh)).lower(),
         "--/renderer/raytracingMotion/enableHydraEngineMasking=false",
         "--/rtx/hydra/supportMultiTickRate=" + str(bool(a.multi)).lower(),
         "--/rtx/rendering/perSensorTickTlas=" + str(bool(a.multi)).lower(),
         "--/log/file=" + str(a.out / "kit.log")]
if a.engines != "all":
    flags += ["--/renderer/raytracingMotion/enableHydraEngineMasking=true",
              "--/renderer/raytracingMotion/enabledForHydraEngines=" + a.engines]
app = SimulationApp({"headless": True, "multi_gpu": False, "fast_shutdown": True,
                     "width": 320, "height": 240, "limit_cpu_threads": 8,
                     "extra_args": flags})

try:
    import carb.settings
    import numpy as np
    import omni.kit.app
    import omni.replicator.core as rep
    import omni.timeline
    import omni.usd
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, Vt
    from isaacsim.sensors.experimental.rtx import parse_generic_model_output_data

    settings = carb.settings.get_settings()
    result["effective_settings"] = {key: settings.get(key) for key in (
        "/renderer/raytracingMotion/enabled", "/renderer/raytracingMotion/enableHydraEngineMasking",
        "/renderer/raytracingMotion/enabledForHydraEngines", "/rtx/hydra/supportMultiTickRate",
        "/rtx/rendering/perSensorTickTlas", "/app/useFabricSceneDelegate")}
    result["kit_build"] = omni.kit.app.get_app().get_build_version()
    phase("new_stage", settings=result["effective_settings"])
    context = omni.usd.get_context()
    context.new_stage()
    stage = context.get_stage()
    stage.SetEditTarget(stage.GetRootLayer())
    stage.DefinePrim("/World", "Xform")
    stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
    UsdGeom.SetStageMetersPerUnit(stage, 1)
    UsdGeom.SetStageUpAxis(stage, "Z")
    stage.SetTimeCodesPerSecond(60)
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(600)

    def box(path, center, size):
        cube = UsdGeom.Cube.Define(stage, path)
        cube.CreateSizeAttr(1.)
        xf = UsdGeom.XformCommonAPI(cube)
        xf.SetTranslate(Gf.Vec3d(*center))
        xf.SetScale(Gf.Vec3f(*size))

    for axis in range(3):
        for sign in (-1, 1):
            center = [0.] * 3
            center[axis] = sign * 10.1
            size = [20.4] * 3
            size[axis] = .2
            box(f"/World/Chamber/wall_{axis}_{'neg' if sign < 0 else 'pos'}", center, size)
    UsdLux.DomeLight.Define(stage, "/World/Light").CreateIntensityAttr(500)
    fill = UsdLux.SphereLight.Define(stage, "/World/FillLight")
    fill.CreateIntensityAttr(3000)
    fill.CreateRadiusAttr(.5)
    UsdGeom.XformCommonAPI(fill).SetTranslate(Gf.Vec3d(0, -4, 4))

    if a.geometry != "mesh":
        phase("load_source", source=a.source)
        source_stage = Usd.Stage.Open(a.source)
        source_root = source_stage.GetDefaultPrim()
        roots = list(source_stage.GetPseudoRoot().GetChildren())
        result["source_roots"] = [{"path": str(r.GetPath()), "type": r.GetTypeName(),
                                   "attributes": [x.GetName() for x in r.GetAttributes()]} for r in roots]
        if not source_root:
            if len(roots) != 1:
                raise RuntimeError("Source has no defaultPrim and multiple roots; specify a wrapper")
            source_root = roots[0]
        asset = stage.OverridePrim("/World/Asset")
        if not asset.GetReferences().AddReference(a.source, source_root.GetPath()):
            raise RuntimeError("Failed to reference source asset")
        phase("source_loaded")
        if a.geometry == "full":
            # Do not execute persisted action graphs or source render products.
            for prim in list(stage.Traverse()):
                if prim and prim.GetTypeName() in {"OmniGraph", "RenderProduct", "RenderSettings", "OmniLidar", "OmniRadar"}:
                    prim.SetActive(False)
        else:
            bound = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render", "proxy"]).ComputeWorldBound(asset).ComputeAlignedRange()
            if not bound.IsEmpty():
                center = bound.GetMidpoint()
                extent = bound.GetSize()
                scale = 2.0 / max(max(extent), 1.e-6)
                xf = UsdGeom.Xformable(asset)
                xf.ClearXformOpOrder()
                op = xf.AddTransformOp()
                matrix = Gf.Matrix4d(1.)
                matrix.SetScale(scale)
                matrix.SetTranslateOnly(Gf.Vec3d(4, 0, 0) - center * scale)
                op.Set(matrix)
                if a.moving == "gaussian":
                    for frame in range(0, 601):
                        m = Gf.Matrix4d(matrix)
                        m.SetTranslateOnly(matrix.ExtractTranslation() + Gf.Vec3d(0, math.sin(frame / 60.), 0))
                        op.Set(m, frame)
        if a.gaussian_state == "hidden":
            UsdGeom.Imageable(asset).CreateVisibilityAttr().Set("invisible")
        elif a.gaussian_state == "inactive":
            asset.SetActive(False)

    if a.exclude_gaussians:
        excluded = []
        for prim in list(stage.Traverse()):
            if prim and "particlefield" in prim.GetTypeName().lower():
                excluded.append(str(prim.GetPath()))
                prim.SetActive(False)
        variants = []
        for prim in list(stage.Traverse()):
            sets = prim.GetVariantSets()
            if sets.HasVariantSet("visualization"):
                vs = sets.GetVariantSet("visualization")
                names = vs.GetVariantNames()
                variants.append({"path": str(prim.GetPath()), "choices": names})
                if "mesh" in names:
                    vs.SetVariantSelection("mesh")
        result["mesh_isolation"] = {"excluded_gaussians": excluded, "visualization_variants": variants}

    types = Counter()
    candidates = []
    for prim in stage.Traverse():
        types[prim.GetTypeName()] += 1
        attrs = [x.GetName() for x in prim.GetAttributes()]
        markers = (prim.GetTypeName() + " " + " ".join(prim.GetAppliedSchemas()) + " " + " ".join(attrs)).lower()
        if any(x in markers for x in ["gaussian", "particlefield", "nurec", "splat"]):
            candidates.append({"path": str(prim.GetPath()), "type": prim.GetTypeName(),
                               "schemas": list(prim.GetAppliedSchemas()), "attributes": attrs})
    result["geometry"] = {"type_counts": dict(types), "gaussian_candidates": candidates[:50]}
    if a.geometry == "gaussian" and a.gaussian_state != "inactive" and not a.exclude_gaussians and not candidates:
        raise RuntimeError("Invalid Gaussian experiment: no Gaussian prim was composed")

    source_layers = []
    for layer in stage.GetUsedLayers():
        if layer != stage.GetRootLayer() and not layer.anonymous:
            layer.SetPermissionToEdit(False)
            layer.SetPermissionToSave(False)
            source_layers.append(layer.identifier)
    result["source_layers"] = source_layers
    phase("scene_inspected", types=dict(types), gaussian_candidates=len(candidates))

    if not a.inspect_only:
        sensor = stage.DefinePrim("/World/Sensor", "OmniLidar")
        sensor.GetReferences().AddReference("/root/gpufree-data/IsaacSim_Asset/sensor_set/lidar_set/NZ3/config/NZ3_scan.usda")
        # Reduce the reference model to eight channels; all edits target the new root.
        for attr in sensor.GetAttributes():
            if ":emitterState:" in attr.GetName():
                value = attr.Get()
                if value is not None and hasattr(value, "__len__") and len(value) > 8:
                    attr.Set(type(value)(list(value)[:8]))
        def set_attr(name, value):
            attr = sensor.GetAttribute(name)
            if not attr or not attr.Set(value):
                raise RuntimeError("Cannot author sensor attribute: " + name)
        overrides = {"scanType": "ROTARY", "instantLidar": False, "numberOfEmitters": 8,
                     "numberOfChannels": 8, "numLines": 1, "numRaysPerLine": [8],
                     "maxReturns": 1, "scanRateBaseHz": 10, "patternFiringRateHz": 1000,
                     "accumulateOutputs": True, "rangeAccuracyM": 0., "nearRangeM": .1,
                     "farRangeM": 100., "rangeOffsetM": 0., "outputFrameOfReference": "SENSOR",
                     "outputMotionCompensationState": "NONCOMPENSATED",
                     "emitterState:s001:azimuthDeg": [0.] * 8,
                     "emitterState:s001:elevationDeg": [-15., -10., -5., 0., 3., 5., 10., 15.],
                     "emitterState:s001:fireTimeNs": [0] * 8,
                     "emitterState:s001:channelId": list(range(1, 9)),
                     "emitterState:s001:bank": [0] * 8}
        for name, value in overrides.items():
            set_attr("omni:sensor:Core:" + name, value)
        set_attr("omni:sensor:tickRate", 10.)
        set_attr("_replicator:rendervar:GenericModelOutput:channels", ["BASIC"])
        if a.moving == "sensor":
            xf = UsdGeom.Xformable(sensor)
            xf.ClearXformOpOrder()
            op = xf.AddTranslateOp()
            op.Set(Gf.Vec3d(0))
            for frame in range(601):
                op.Set(Gf.Vec3d(0, math.sin(frame / 60.), 0), frame)
        phase("attach_sensor")
        product = rep.create.render_product(str(sensor.GetPath()), (1, 1),
                                             name="BVHProbe", render_vars=["GenericModelOutput"])
        annotator = rep.AnnotatorRegistry.get_annotator("GenericModelOutput", device="cpu", do_array_copy=True)
        annotator.attach([product.path])
        if a.capture:
            camera = UsdGeom.Camera.Define(stage, "/World/DiagnosticCamera")
            camera.CreateFocalLengthAttr(35.)
            camera.CreateClippingRangeAttr(Gf.Vec2f(.05, 100.))
            UsdGeom.Xformable(camera).AddTransformOp().Set(
                Gf.Matrix4d().SetLookAt(Gf.Vec3d(0, -5, 2), Gf.Vec3d(4, 0, 0), Gf.Vec3d(0, 0, 1)).GetInverse())
            rgb_product = rep.create.render_product(str(camera.GetPath()), (640, 480), name="DiagnosticRGB")
            rgb_annotator = rep.AnnotatorRegistry.get_annotator("rgb", device="cpu")
            rgb_annotator.attach([rgb_product.path])
    for layer in stage.GetUsedLayers():
        if layer != stage.GetRootLayer() and not layer.anonymous:
            layer.SetPermissionToEdit(False)
            layer.SetPermissionToSave(False)
    stage.GetRootLayer().Export(str(a.out / "experiment.usda"))

    if not a.inspect_only:
        timeline = omni.timeline.get_timeline_interface()
        seen = set()
        for cycle in range(a.replays + 1):
            phase("play", cycle=cycle)
            timeline.play()
            for frame in range(a.frames):
                app.update()
                if a.capture and frame == a.frames - 1:
                    from PIL import Image
                    rgb = rgb_annotator.get_data()
                    if isinstance(rgb, dict):
                        rgb = rgb.get("data")
                    if rgb is not None and np.asarray(rgb).size:
                        Image.fromarray(np.asarray(rgb)).save(a.out / f"rgb_cycle_{cycle}.png")
                raw = annotator.get_data()
                if isinstance(raw, dict):
                    raw = raw.get("data")
                if raw is None or len(raw) == 0:
                    continue
                g = parse_generic_model_output_data(raw)
                key = (cycle, int(g.frameId))
                if key in seen or not g.numElements:
                    continue
                seen.add(key)
                xyz = np.column_stack((g.x, g.y, g.z)).copy()
                row = {"cycle": cycle, "frame": frame, "frame_id": int(g.frameId),
                       "count": int(g.numElements), "scan_complete": int(g.scanComplete),
                       "timeline_time": timeline.get_current_time(),
                       "finite_count": int(np.isfinite(xyz).all(axis=1).sum()),
                       "range_min": float(np.linalg.norm(xyz, axis=1).min()),
                       "range_max": float(np.linalg.norm(xyz, axis=1).max())}
                row["near_hits_lt8m"] = int((np.linalg.norm(xyz, axis=1) < 8).sum())
                row["wall_error_max_m"] = float(np.min(np.abs(np.abs(xyz) - 10.), axis=1).max())
                for key2 in ("timestampNs", "startTimeNs", "endTimeNs", "scanStartTimeNs"):
                    try:
                        row[key2] = int(getattr(g, key2))
                    except (AttributeError, TypeError, ValueError):
                        pass
                if len(result["samples"]) < 6 or frame >= a.frames - 10:
                    arrays = {"xyz": xyz}
                    for key2 in ("emitterId", "channelId", "timeOffsetNs", "flags", "intensity"):
                        try:
                            arrays[key2] = np.asarray(getattr(g, key2)).copy()
                        except AttributeError:
                            pass
                    filename = f"sample_{cycle}_{frame:04d}.npz"
                    np.savez_compressed(a.out / filename, **arrays)
                    row["file"] = filename
                result["samples"].append(row)
                if frame % 30 == 0:
                    phase("collecting", cycle=cycle, frame=frame, count=row["count"])
            phase("stop", cycle=cycle)
            timeline.stop()
            for _ in range(4):
                app.update()
        annotator.detach([product.path])
        product.destroy()
        if a.capture:
            rgb_annotator.detach([rgb_product.path])
            rgb_product.destroy()
        result["status"] = "data_collected" if result["samples"] else "no_sensor_data"
    else:
        result["status"] = "inspection_complete"
    phase("completed", samples=len(result["samples"]))
except BaseException:
    result["status"] = "python_error"
    result["error"] = traceback.format_exc()
    print(result["error"], flush=True)
finally:
    (a.out / "result.json").write_text(json.dumps(result, indent=2))
    app.close(wait_for_replicator=False)
