from __future__ import annotations

from typing import Dict

from ...common.box_geometry import extract_semantic_boxes
from ...common.models import (
    ModuleResult,
    SemanticBoxSet,
    YoloAnnotationSet,
    YoloDetection,
)
from ...pipeline.frame_context import FrameArtifactStore, FrameContext
from ...pipeline.module_base import PipelineModule, RunContext
from ...pipeline.module_registry import register_module
from ...pipeline.orchestrator_config import ModuleSpec
from .module_config import SemanticYoloBoxesConfig, load_module_config


@register_module("semantic_yolo_boxes")
class SemanticYoloBoxesModule(PipelineModule):
    def __init__(
        self,
        spec: ModuleSpec,
        config: SemanticYoloBoxesConfig,
    ) -> None:
        super().__init__(
            module_id=spec.module_id,
            depends_on=spec.depends_on,
            output_dir=config.output.directory,
            class_names=config.class_names,
        )
        self.config = config

    @classmethod
    def from_config(
        cls,
        spec: ModuleSpec,
        run_context: RunContext,
    ) -> "SemanticYoloBoxesModule":
        return cls(spec, load_module_config(spec, run_context))

    def process_frame(
        self,
        frame: FrameContext,
        artifacts: FrameArtifactStore,
    ) -> ModuleResult:
        del artifacts
        semantic_boxes = SemanticBoxSet(
            extract_semantic_boxes(
                frame.semantic,
                self.config.labels_to_ids,
            )
        )
        boxes_by_label = semantic_boxes.by_label()
        detections = []
        small_masks = 0
        missing_masks = 0

        for target in self.config.targets:
            for label in target.semantic_labels:
                semantic_box = boxes_by_label.get(label)
                if semantic_box is None:
                    missing_masks += 1
                    continue
                if semantic_box.pixel_count < self.config.min_pixels:
                    small_masks += 1
                    continue
                detections.append(
                    YoloDetection(
                        class_id=target.yolo_id,
                        class_name=target.yolo_name,
                        box=semantic_box.box,
                    )
                )

        return ModuleResult(
            artifacts={"semantic_boxes": semantic_boxes},
            annotation=YoloAnnotationSet(tuple(detections)),
            metrics={
                "small_masks": small_masks,
                "missing_masks": missing_masks,
            },
        )
