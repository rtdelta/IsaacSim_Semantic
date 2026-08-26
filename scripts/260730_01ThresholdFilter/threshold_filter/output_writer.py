from __future__ import annotations

import shutil
from pathlib import Path
from typing import Sequence

from .atomic_io import materialize_image, write_text
from .config import RunConfig
from .models import FileIndex, FrameResult


class OutputWriter:
    def __init__(
        self,
        config: RunConfig,
        staging_root: Path,
        file_index: FileIndex,
    ) -> None:
        self.config = config
        self.staging_root = staging_root
        self.file_index = file_index
        self.tooth_output = staging_root / "modules" / "tooth_boxes"
        self.group_output = staging_root / "modules" / "tooth_group"

    def prepare(self) -> None:
        if self.config.execution.dry_run:
            return
        self.tooth_output.mkdir(parents=True, exist_ok=True)
        self.group_output.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(
            self.file_index.tooth.classes_path,
            self.tooth_output / "classes.txt",
        )
        shutil.copyfile(
            self.file_index.group.classes_path,
            self.group_output / "classes.txt",
        )

    def _write_label(self, path: Path, content: str) -> None:
        if content or self.config.output.keep_empty_label_files:
            write_text(path, content)

    def write_frame(self, result: FrameResult) -> None:
        if self.config.execution.dry_run:
            return
        frame_id = result.frame_id
        if result.tooth_output_text is not None:
            self._write_label(
                self.tooth_output / result.tooth_label_name,
                result.tooth_output_text,
            )
            if self.config.output.image_mode != "none":
                source_image = self.file_index.tooth.images[frame_id]
                materialize_image(
                    source_image,
                    self.tooth_output / source_image.name,
                    self.config.output.image_mode,
                )

        if (
            result.group_label_name is not None
            and result.group_output_text is not None
        ):
            self._write_label(
                self.group_output / result.group_label_name,
                result.group_output_text,
            )
            if self.config.output.image_mode != "none":
                source_image = self.file_index.group.images[frame_id]
                materialize_image(
                    source_image,
                    self.group_output / source_image.name,
                    self.config.output.image_mode,
                )

    def verify(
        self,
        results: Sequence[FrameResult],
    ) -> int:
        if self.config.execution.dry_run:
            return 0
        level = self.config.performance.verification_level
        if level == "none":
            return 0
        candidates = [
            result for result in results if result.tooth_output_text is not None
        ]
        if level == "full":
            selected = candidates
        else:
            requested = self.config.performance.verification_sample_frames
            if requested <= 0 or not candidates:
                return 0
            count = min(requested, len(candidates))
            if count == 1:
                selected = [candidates[0]]
            else:
                positions = sorted(
                    {
                        round(index * (len(candidates) - 1) / (count - 1))
                        for index in range(count)
                    }
                )
                selected = [candidates[position] for position in positions]

        for result in selected:
            tooth_label = self.tooth_output / result.tooth_label_name
            should_exist = bool(result.tooth_output_text) or (
                self.config.output.keep_empty_label_files
            )
            if should_exist:
                if not tooth_label.is_file():
                    raise ValueError(f"verification missing label: {tooth_label}")
                actual = tooth_label.read_text(encoding="utf-8")
                if actual != result.tooth_output_text:
                    raise ValueError(
                        f"verification content mismatch: {tooth_label}"
                    )
            elif tooth_label.exists():
                raise ValueError(
                    f"verification found unexpected empty label: {tooth_label}"
                )
            if self.config.output.image_mode != "none":
                source_image = self.file_index.tooth.images[result.frame_id]
                output_image = self.tooth_output / source_image.name
                if not output_image.exists():
                    raise ValueError(
                        f"verification missing tooth image: {output_image}"
                    )

            if (
                result.group_label_name is not None
                and result.group_output_text is not None
            ):
                group_label = self.group_output / result.group_label_name
                group_should_exist = bool(result.group_output_text) or (
                    self.config.output.keep_empty_label_files
                )
                if group_should_exist:
                    if not group_label.is_file():
                        raise ValueError(
                            f"verification missing group label: {group_label}"
                        )
                    actual = group_label.read_text(encoding="utf-8")
                    if actual != result.group_output_text:
                        raise ValueError(
                            f"verification content mismatch: {group_label}"
                        )
                elif group_label.exists():
                    raise ValueError(
                        f"verification found unexpected group label: {group_label}"
                    )
        return len(selected)
