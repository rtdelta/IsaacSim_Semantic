"""Runtime adapter for a native fisheye model already authored on a USD Camera."""

from semantic_world_v04.plugins.sensors.fisheye_camera import detected_projection

from .camera_driver import CameraRuntimeDriver


class FisheyeRuntimeDriver(CameraRuntimeDriver):
    backend_id = "native_usd"

    def preflight(self, stage):
        super().preflight(stage)
        from semantic_world_v04.stage.omni_adapter import read_fisheye_parameters

        parameters = read_fisheye_parameters(stage, self.sensor.prim_path)
        projection = detected_projection(parameters)
        if not projection:
            raise RuntimeError(
                f"camera {self.sensor_id} has no native fisheye projection at Runtime"
            )

    def initialize(self, stage):
        super().initialize(stage)
        from semantic_world_v04.stage.omni_adapter import read_fisheye_parameters

        self.effective_parameters_snapshot.update(
            read_fisheye_parameters(stage, self.sensor.prim_path)
        )
        self.effective_parameters_snapshot["backend_id"] = self.backend_id
        self.effective_parameters_snapshot["projection_model"] = detected_projection(
            self.effective_parameters_snapshot
        )
