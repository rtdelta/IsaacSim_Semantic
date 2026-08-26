"""Filesystem packet sink writing only inside a frame transaction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import SensorConfig
from .models import SensorPacket, jsonable
from .semantic_mapping import SemanticMapping
from .transactions import FrameTransaction


def _numpy(value: Any) -> Any:
    import numpy as np

    if isinstance(value, np.ndarray):
        return value
    for method in ("numpy", "cpu"):
        candidate = getattr(value, method, None)
        if callable(candidate):
            try:
                value = candidate()
            except Exception:
                pass
    if hasattr(value, "numpy") and callable(value.numpy):
        try:
            value = value.numpy()
        except Exception:
            pass
    try:
        array = np.asarray(value)
        return array if array.dtype != object else None
    except Exception:
        return None


class FilesystemSink:
    def __init__(self, semantic_mapping: SemanticMapping | None = None) -> None:
        self.semantic_mapping = semantic_mapping

    def _prefix(self, spec: SensorConfig, packet: SensorPacket) -> Path:
        folder = spec.output.folder or f"sensors/{spec.sensor_id}"
        return Path(folder) / packet.variant_id / f"frame_{packet.frame_id:08d}"

    @staticmethod
    def _json(path: Path, value: Any) -> None:
        path.write_text(
            json.dumps(jsonable(value), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def write(
        self, transaction: FrameTransaction, spec: SensorConfig, packet: SensorPacket
    ) -> tuple[str, ...]:
        import numpy as np

        prefix = self._prefix(spec, packet)
        written: list[str] = []
        for modality, value in packet.payloads.items():
            data = value.get("data") if isinstance(value, dict) and "data" in value else value
            info = value.get("info", {}) if isinstance(value, dict) else {}
            array = _numpy(data)
            base = prefix / modality
            if modality == "semantic_segmentation" and array is not None and self.semantic_mapping:
                # The raw annotator IDs are renderer-local and redundant once
                # normalized.  Persist only the stable dataset IDs requested by
                # downstream users plus their visualization.
                mapped = self.semantic_mapping.remap(array, info)
                mapped_target = transaction.path(prefix / "semantic_class_id.npy")
                np.save(mapped_target, mapped, allow_pickle=False)
                color_target = transaction.path(prefix / "semantic_color.png")
                from PIL import Image

                Image.fromarray(self.semantic_mapping.colorize(mapped), mode="RGB").save(color_target)
                written.extend(
                    [
                        mapped_target.relative_to(transaction.stage_root).as_posix(),
                        color_target.relative_to(transaction.stage_root).as_posix(),
                    ]
                )
            elif modality == "rgb" and array is not None and array.ndim == 3:
                from PIL import Image

                rgb = array[..., :3].astype(np.uint8, copy=False)
                target = transaction.path(base.with_suffix(".png"))
                Image.fromarray(rgb, mode="RGB").save(target)
                written.append(str(target.relative_to(transaction.stage_root).as_posix()))
            elif isinstance(data, (bytes, bytearray, memoryview)):
                target = transaction.path(base.with_suffix(".bin"))
                target.write_bytes(bytes(data))
                written.append(str(target.relative_to(transaction.stage_root).as_posix()))
            elif array is not None:
                target = transaction.path(base.with_suffix(".npy"))
                np.save(target, array, allow_pickle=False)
                written.append(str(target.relative_to(transaction.stage_root).as_posix()))
            else:
                target = transaction.path(base.with_suffix(".json"))
                self._json(target, data)
                written.append(str(target.relative_to(transaction.stage_root).as_posix()))
            if info:
                info_target = transaction.path(prefix / f"{modality}.info.json")
                self._json(info_target, info)
                written.append(info_target.relative_to(transaction.stage_root).as_posix())
        metadata_target = transaction.path(prefix / "packet.json")
        self._json(metadata_target, packet.to_metadata())
        written.append(metadata_target.relative_to(transaction.stage_root).as_posix())
        return tuple(sorted(written))
