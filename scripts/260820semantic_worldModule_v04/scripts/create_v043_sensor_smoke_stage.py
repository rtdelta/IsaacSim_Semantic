"""Create a small validation USD with pinhole, OpenCV fisheye, and RTX LiDAR."""

import argparse
from pathlib import Path

from isaacsim import SimulationApp  # type: ignore


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args, _ = parser.parse_known_args(argv)

    app = SimulationApp(
        {
            "headless": True,
            "multi_gpu": False,
            "max_gpu_count": 1,
            "renderer": "RayTracedLighting",
            "width": 320,
            "height": 240,
        }
    )
    try:
        import numpy as np
        import omni.usd  # type: ignore
        from isaacsim.core.experimental.utils.transform import (
            euler_angles_to_quaternion,
        )
        from isaacsim.sensors.experimental.rtx import Lidar, RtxCamera
        from pxr import Gf, Sdf, UsdGeom, UsdLux

        context = omni.usd.get_context()
        context.new_stage()
        for _ in range(3):
            app.update()
        stage = context.get_stage()

        world = UsdGeom.Xform.Define(stage, "/World")
        _ = world
        light = UsdLux.DomeLight.Define(stage, "/World/DomeLight")
        light.CreateIntensityAttr(900.0)
        for index, (position, color) in enumerate(
            (
                ((5.0, 0.0, 1.0), (1.0, 0.1, 0.1)),
                ((3.0, 3.0, 1.5), (0.1, 1.0, 0.1)),
                ((3.0, -3.0, 2.0), (0.1, 0.1, 1.0)),
                ((0.0, 5.0, 1.0), (1.0, 1.0, 0.1)),
            )
        ):
            cube = UsdGeom.Cube.Define(stage, f"/World/Targets/Cube_{index}")
            cube.CreateSizeAttr(1.5)
            cube.CreateDisplayColorAttr([Gf.Vec3f(*color)])
            xform = UsdGeom.Xformable(cube.GetPrim())
            xform.AddTranslateOp().Set(Gf.Vec3d(*position))

        ground = UsdGeom.Cube.Define(stage, "/World/Ground")
        ground.CreateSizeAttr(1.0)
        ground.CreateDisplayColorAttr([Gf.Vec3f(0.25, 0.25, 0.25)])
        ground_xform = UsdGeom.Xformable(ground.GetPrim())
        ground_xform.AddScaleOp().Set(Gf.Vec3f(30.0, 30.0, 0.1))
        ground_xform.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, -0.6))

        orientation = euler_angles_to_quaternion(
            np.array([0.0, 0.0, -90.0]),
            degrees=True,
            extrinsic=False,
        ).numpy()
        RtxCamera(
            "/World/Sensors/Pinhole",
            translations=np.array([0.0, 0.0, 3.5]),
            orientations=orientation,
        )
        fisheye = RtxCamera(
            "/World/Sensors/Fisheye",
            schemas=["OmniLensDistortionOpenCvFisheyeAPI"],
            attributes={
                "omni:lensdistortion:opencvFisheye:cx": 160.0,
                "omni:lensdistortion:opencvFisheye:cy": 120.0,
                "omni:lensdistortion:opencvFisheye:fx": 145.0,
                "omni:lensdistortion:opencvFisheye:fy": 145.0,
                "omni:lensdistortion:opencvFisheye:k1": 0.05,
                "omni:lensdistortion:opencvFisheye:k2": 0.01,
                "omni:lensdistortion:opencvFisheye:k3": -0.003,
                "omni:lensdistortion:opencvFisheye:k4": -0.0005,
                "omni:lensdistortion:opencvFisheye:imageSize": Gf.Vec2i(320, 240),
            },
            translations=np.array([0.0, 0.0, 3.5]),
            orientations=orientation,
        )
        fisheye.prims[0].GetAttribute("omni:lensdistortion:model").Set(
            "opencvFisheye"
        )
        Lidar.create(
            "/World/Sensors/Lidar",
            config="Example_Rotary",
            translations=np.array([0.0, 0.0, 1.0]),
            aux_output_level="BASIC",
            tick_rate=10.0,
            attributes={
                "omni:sensor:Core:scanRateBaseHz": 10.0,
                "omni:sensor:tickRate": 10.0,
            },
        )

        stage.SetMetadata("metersPerUnit", 1.0)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        if not stage.GetRootLayer().Export(str(output)):
            raise RuntimeError(f"failed to export validation stage: {output}")
        print(f"V04_SENSOR_SMOKE_STAGE={output}", flush=True)
    finally:
        app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
