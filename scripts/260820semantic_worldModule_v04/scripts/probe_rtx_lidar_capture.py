"""Probe RTX LiDAR annotator readiness against a real USD Stage.

This is a diagnostic utility for Isaac Sim deployments.  It deliberately keeps
the probe outside the capture Runtime so that SDK timing changes can be
investigated without changing dataset semantics.
"""

import argparse
import json
from pathlib import Path
from typing import Any

from isaacsim import SimulationApp  # type: ignore


def _describe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _describe(item) for key, item in value.items()}
    shape = getattr(value, "shape", None)
    dtype = getattr(value, "dtype", None)
    result = {"type": f"{type(value).__module__}.{type(value).__name__}"}
    if shape is not None:
        result["shape"] = [int(item) for item in shape]
    if dtype is not None:
        result["dtype"] = str(dtype)
    if hasattr(value, "numpy"):
        try:
            array = value.numpy()
            result["numpy_shape"] = [int(item) for item in array.shape]
            result["numpy_dtype"] = str(array.dtype)
            result["numpy_size"] = int(array.size)
        except Exception as exc:  # pragma: no cover - SDK diagnostic path
            result["numpy_error"] = f"{type(exc).__name__}: {exc}"
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True)
    parser.add_argument("--prim-path", default="/World/Sensors/Lidar")
    parser.add_argument("--updates", type=int, default=180)
    parser.add_argument("--report", required=True)
    args, _ = parser.parse_known_args(argv)

    app = SimulationApp(
        {
            "headless": True,
            "renderer": "RayTracedLighting",
            "width": 320,
            "height": 240,
            "multi_gpu": False,
            "max_gpu_count": 1,
        }
    )
    render_product = None
    annotator = None
    try:
        import omni.kit.app  # type: ignore
        import omni.replicator.core as rep  # type: ignore
        import omni.timeline  # type: ignore
        import omni.usd  # type: ignore

        manager = omni.kit.app.get_app().get_extension_manager()
        manager.set_extension_enabled_immediate("isaacsim.sensors.rtx.nodes", True)
        context = omni.usd.get_context()
        if not context.open_stage(args.stage):
            raise RuntimeError(f"could not open Stage: {args.stage}")
        for _ in range(600):
            app.update()
            status = context.get_stage_loading_status()
            if context.get_stage() is not None and int(status[2]) == 0:
                break
        render_product = rep.create.render_product(
            args.prim_path, resolution=(300, 300), name="v043_lidar_probe"
        )
        annotator = rep.AnnotatorRegistry.get_annotator(
            "IsaacExtractRTXSensorPointCloud",
            device="cuda",
            do_array_copy=False,
        )
        render_product_path = getattr(render_product, "path", render_product)
        annotator.attach([render_product_path])
        timeline = omni.timeline.get_timeline_interface()
        timeline.set_current_time(0.0)
        timeline.play()
        observations = []
        for index in range(args.updates):
            app.update()
            raw = annotator.get_data()
            observation = {
                "update": index + 1,
                "timeline_time": float(timeline.get_current_time()),
                "payload": _describe(raw),
            }
            observations.append(observation)
            payload = raw.get("data") if isinstance(raw, dict) else raw
            size = getattr(payload, "size", 0) if payload is not None else 0
            if int(size or 0) > 0:
                break
        timeline.pause()
        report = {
            "stage": args.stage,
            "prim_path": args.prim_path,
            "observations": observations,
        }
        output = Path(args.report)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"V04_LIDAR_PROBE={output}", flush=True)
        print(json.dumps(observations[-1], ensure_ascii=False), flush=True)
    finally:
        if annotator is not None and render_product is not None:
            render_product_path = getattr(render_product, "path", render_product)
            annotator.detach([render_product_path])
        if render_product is not None:
            render_product.destroy()
        app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
