from __future__ import annotations

from typing import Optional, Sequence, Tuple

from ...common.box_geometry import (
    envelope_from_endpoint_boxes,
    select_image_extrema,
)
from ...common.models import (
    ModuleResult,
    SemanticBox,
    SemanticBoxSet,
    YoloAnnotationSet,
    YoloDetection,
)
from ...pipeline.frame_context import FrameArtifactStore, FrameContext
from ...pipeline.module_base import PipelineModule, RunContext
from ...pipeline.module_registry import register_module
from ...pipeline.orchestrator_config import ModuleSpec
from .module_config import ToothGroupYoloConfig, load_module_config


@register_module("tooth_group_yolo")
class ToothGroupYoloModule(PipelineModule):
    def __init__(
        self,
        spec: ModuleSpec,
        config: ToothGroupYoloConfig,
    ) -> None:
        super().__init__(
            module_id=spec.module_id,
            depends_on=spec.depends_on,
            output_dir=config.output.directory,
            class_names=(config.yolo_name,),
        )
        self.config = config

    @classmethod
    def from_config(
        cls,
        spec: ModuleSpec,
        run_context: RunContext,
    ) -> "ToothGroupYoloModule":
        return cls(spec, load_module_config(spec, run_context))

    def validate(self, run_context: RunContext) -> None:
        super().validate(run_context)
        source_module_id, separator, artifact_name = (
            self.config.source_artifact.partition(".")
        )
        if not separator or not source_module_id or not artifact_name:
            raise ValueError(
                f"module {self.module_id!r} source_artifact must be "
                "'<module_id>.<artifact_name>'"
            )
        if source_module_id not in self.depends_on:
            raise ValueError(
                f"module {self.module_id!r} consumes "
                f"{self.config.source_artifact!r} but does not depend on "
                f"{source_module_id!r}"
            )

    def _eligible_boxes(
        self,
        semantic_boxes: SemanticBoxSet,
    ) -> Tuple[SemanticBox, ...]:
        return tuple(
            item
            for item in semantic_boxes.boxes
            if item.pixel_count >= self.config.min_pixels
        )

    def _select_endpoints(
        self,
        eligible: Sequence[SemanticBox],
    ) -> Optional[Tuple[SemanticBox, SemanticBox]]:
        selector = self.config.endpoint_selector
        by_label = {item.semantic_label: item for item in eligible}

        if selector.selector_type == "semantic_labels":
            selected = [by_label.get(label) for label in selector.labels]
            if all(item is not None for item in selected):
                return selected[0], selected[1]  # type: ignore[return-value]
        else:
            candidates = [
                by_label[label]
                for label in selector.labels
                if label in by_label
            ]
            if len(candidates) >= 2:
                return select_image_extrema(candidates)

        if self.config.missing_policy == "visible_extrema" and len(eligible) >= 2:
            return select_image_extrema(eligible)
        return None

    def _missing_result(self) -> ModuleResult:
        metrics = {"missing_endpoints": 1}
        policy = self.config.missing_policy
        if policy in {"exclude_frame", "visible_extrema"}:
            return ModuleResult(
                disposition="exclude",
                metrics=metrics,
            )
        if policy == "empty_label":
            return ModuleResult(
                annotation=YoloAnnotationSet(()),
                metrics=metrics,
            )
        raise ValueError("required endpoint tooth boxes are unavailable")

    def process_frame(
        self,
        frame: FrameContext,
        artifacts: FrameArtifactStore,
    ) -> ModuleResult:
        del frame
        source = artifacts.get(self.config.source_artifact)
        if not isinstance(source, SemanticBoxSet):
            raise TypeError(
                f"artifact {self.config.source_artifact!r} must be SemanticBoxSet"
            )

        eligible = self._eligible_boxes(source)
        endpoints = self._select_endpoints(eligible)
        if endpoints is None:
            return self._missing_result()

        group_box = envelope_from_endpoint_boxes(
            endpoints[0].box,
            endpoints[1].box,
        )
        return ModuleResult(
            artifacts={"group_box": group_box},
            annotation=YoloAnnotationSet(
                (
                    YoloDetection(
                        class_id=self.config.yolo_id,
                        class_name=self.config.yolo_name,
                        box=group_box,
                    ),
                )
            ),
            metrics={"missing_endpoints": 0},
        )
