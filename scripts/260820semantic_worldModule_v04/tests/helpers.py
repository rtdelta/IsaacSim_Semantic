from semantic_world_v04.core.models import (
    CaptureSchedule,
    ModalityDefinition,
    OutputPolicy,
    ProjectDefinition,
    RenderProfile,
    SensorDefinition,
    StageReference,
    VariantDefinition,
)


def make_project(output_root: str = "output") -> ProjectDefinition:
    return ProjectDefinition(
        project_id="excavator-demo",
        name="Excavator Demo",
        stage=StageReference("scene.usda"),
        sensors=[
            SensorDefinition(
                sensor_id="boom_camera",
                plugin="pinhole_camera",
                prim_path="/World/Excavator/Camera",
            )
        ],
        variants=[
            VariantDefinition(
                variant_id="full_scene",
                strategy="full_scene",
                modalities_by_sensor={
                    "boom_camera": ["rgb", "semantic_id", "semantic_color"]
                },
            ),
            VariantDefinition(
                variant_id="excavator_only",
                strategy="include_paths",
                include_paths=["/World/Excavator", "/World/Light"],
                modalities_by_sensor={
                    "boom_camera": ["semantic_id", "semantic_color"]
                },
            ),
        ],
        modalities=[
            ModalityDefinition("rgb", "rgb"),
            ModalityDefinition("semantic_id", "semantic_id"),
            ModalityDefinition("semantic_color", "semantic_color"),
        ],
        render=RenderProfile(
            renderer="PathTracing",
            resolution_width=320,
            resolution_height=180,
            warmup_frames=2,
            rt_subframes=1,
            spp_per_frame=1,
            total_spp=1,
        ),
        capture=CaptureSchedule(
            physics_hz=60,
            capture_fps=10,
            frame_count=2,
            segment_frames=1,
        ),
        output=OutputPolicy(root_dir=output_root),
    )

