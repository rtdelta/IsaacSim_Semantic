"""Probe the deployed Isaac/Kit sensor APIs and write a machine-readable report."""

import argparse
import inspect
import json
import platform
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _attempt(callback):
    try:
        return {"available": True, "details": callback()}
    except BaseException as exc:
        return {
            "available": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=4),
        }


def _nvidia_smi():
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=15,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "nvidia-smi failed")
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args, _ = parser.parse_known_args(argv)

    from isaacsim import SimulationApp  # type: ignore

    app = SimulationApp(
        {
            "headless": True,
            "multi_gpu": False,
            "max_gpu_count": 1,
            "renderer": "RayTracedLighting",
        }
    )
    report = {
        "schema_version": 1,
        "probe": "semantic_world_v04_v043_sensor_capabilities",
        "created_at_utc": _utc_now(),
        "python": {
            "executable": sys.executable,
            "version": sys.version,
            "platform": platform.platform(),
        },
        "gpu": _attempt(_nvidia_smi),
        "extensions": {},
        "apis": {},
    }
    try:
        import omni.kit.app  # type: ignore
        import omni.replicator.core as rep  # type: ignore

        kit_app = omni.kit.app.get_app()
        manager = kit_app.get_extension_manager()
        for extension_id in (
            "isaacsim.sensors.experimental.rtx",
            "isaacsim.sensors.rtx.nodes",
            "omni.usd.schema.omni_sensors",
            "omni.replicator.core",
        ):
            result = _attempt(
                lambda extension_id=extension_id: manager.set_extension_enabled_immediate(
                    extension_id, True
                )
            )
            result["enabled"] = bool(manager.is_extension_enabled(extension_id))
            report["extensions"][extension_id] = result
        for _ in range(8):
            app.update()

        def camera_api():
            from isaacsim.sensors.experimental.rtx import CameraSensor, RtxCamera

            return {
                "RtxCamera_signature": str(inspect.signature(RtxCamera)),
                "CameraSensor_signature": str(inspect.signature(CameraSensor)),
                "opencv_fisheye_schema": "OmniLensDistortionOpenCvFisheyeAPI",
                "opencv_fisheye_attributes": [
                    "omni:lensdistortion:model",
                    "omni:lensdistortion:opencvFisheye:cx",
                    "omni:lensdistortion:opencvFisheye:cy",
                    "omni:lensdistortion:opencvFisheye:fx",
                    "omni:lensdistortion:opencvFisheye:fy",
                    "omni:lensdistortion:opencvFisheye:k1",
                    "omni:lensdistortion:opencvFisheye:k2",
                    "omni:lensdistortion:opencvFisheye:k3",
                    "omni:lensdistortion:opencvFisheye:k4",
                    "omni:lensdistortion:opencvFisheye:imageSize",
                ],
            }

        def lidar_api():
            from isaacsim.sensors.experimental.rtx import (
                Lidar,
                LidarSensor,
                SUPPORTED_LIDAR_CONFIGS,
                parse_generic_model_output_data,
            )

            return {
                "Lidar_signature": str(inspect.signature(Lidar)),
                "LidarSensor_signature": str(inspect.signature(LidarSensor)),
                "supported_config_count": len(SUPPORTED_LIDAR_CONFIGS),
                "sample_configs": list(SUPPORTED_LIDAR_CONFIGS)[:12],
                "parse_generic_model_output_data": bool(
                    callable(parse_generic_model_output_data)
                ),
                "preferred_annotator": "IsaacExtractRTXSensorPointCloud",
            }

        report["apis"]["fisheye_camera"] = _attempt(camera_api)
        report["apis"]["rtx_lidar"] = _attempt(lidar_api)

        annotators = {}
        for name in (
            "rgb",
            "semantic_segmentation",
            "distance_to_camera",
            "normals",
            "instance_segmentation",
            "GenericModelOutput",
            "IsaacExtractRTXSensorPointCloud",
            "IsaacCreateRTXLidarScanBuffer",
            "RtxSensorCpuIsaacCreateRTXLidarScanBuffer",
        ):
            annotators[name] = _attempt(
                lambda name=name: type(
                    rep.AnnotatorRegistry.get_annotator(name)
                ).__name__
            )
        report["apis"]["annotators"] = annotators
        try:
            report["kit_build_version"] = str(kit_app.get_build_version())
        except Exception:
            report["kit_build_version"] = "unknown"
    finally:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"V04_CAPABILITY_REPORT={output}", flush=True)
        app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
