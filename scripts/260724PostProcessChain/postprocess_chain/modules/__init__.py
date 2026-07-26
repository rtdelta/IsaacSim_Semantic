"""Built-in module registration."""

from .semantic_yolo_boxes.module import SemanticYoloBoxesModule
from .tooth_group_yolo.module import ToothGroupYoloModule

__all__ = ["SemanticYoloBoxesModule", "ToothGroupYoloModule"]
