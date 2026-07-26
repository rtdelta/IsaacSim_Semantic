from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Mapping, Tuple

from ..common.models import ModuleResult
from ..common.output_writer import prepare_yolo_output
from .frame_context import FrameArtifactStore, FrameContext
from .orchestrator_config import ModuleSpec


@dataclass(frozen=True)
class RunContext:
    output_root: Path
    label_to_id: Mapping[str, int]
    expected_dtype: str
    overwrite: bool
    image_mode: str


class PipelineModule(ABC):
    type_name: ClassVar[str]

    def __init__(
        self,
        module_id: str,
        depends_on: Tuple[str, ...],
        output_dir: Path,
        class_names: Tuple[str, ...],
    ) -> None:
        self.module_id = module_id
        self.depends_on = depends_on
        self.output_dir = output_dir
        self.class_names = class_names

    @classmethod
    @abstractmethod
    def from_config(
        cls,
        spec: ModuleSpec,
        run_context: RunContext,
    ) -> "PipelineModule":
        raise NotImplementedError

    def validate(self, run_context: RunContext) -> None:
        if not self.class_names:
            raise ValueError(f"module {self.module_id!r} has no YOLO classes")

    def prepare(self, run_context: RunContext) -> None:
        prepare_yolo_output(self.output_dir, self.class_names)

    @abstractmethod
    def process_frame(
        self,
        frame: FrameContext,
        artifacts: FrameArtifactStore,
    ) -> ModuleResult:
        raise NotImplementedError

    def finalize(self) -> None:
        return None
