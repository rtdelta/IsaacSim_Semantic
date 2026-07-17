"""Replicator Writer for stable semantic NPY and custom-color PNG output."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

import numpy as np
from omni.replicator.core import AnnotatorRegistry, Writer
from omni.replicator.core import functional as F

from semantic_mapping import SemanticMapping


class SemanticDatasetWriter(Writer):
    version = "1.0.0"

    def __init__(
        self,
        backend: Any,
        semantic_schema: str,
        rgb: bool = True,
        save_runtime_ids: bool = True,
        strict_mapping: bool = True,
        frame_padding: int = 4,
    ) -> None:
        self.data_structure = "renderProduct"
        self.backend = backend
        self._backend = backend
        self.mapping = SemanticMapping(semantic_schema)
        self._frame_id = 0
        self._frame_padding = frame_padding
        self._save_rgb = rgb
        self._save_runtime_ids = save_runtime_ids
        self._strict_mapping = strict_mapping
        self.version = type(self).version
        self.annotators = []
        if rgb:
            self.annotators.append(AnnotatorRegistry.get_annotator("rgb"))
        self.annotators.append(
            AnnotatorRegistry.get_annotator(
                "semantic_segmentation",
                init_params={"colorize": False, "semanticFilter": "class:*"},
            )
        )
        self.backend.schedule(F.write_json, data=self.mapping.schema, path="semantic_mapping.json")

    @staticmethod
    def _find(render_product_data: dict[str, Any], annotator_name: str) -> Any:
        if annotator_name in render_product_data:
            return render_product_data[annotator_name]
        for key, value in render_product_data.items():
            if key.startswith(annotator_name):
                return value
        return None

    @staticmethod
    def _entry_data(entry: Any) -> np.ndarray:
        return np.asarray(entry["data"] if isinstance(entry, dict) and "data" in entry else entry)

    @staticmethod
    def _runtime_id_image(entry: dict[str, Any]) -> np.ndarray:
        data = np.asarray(entry["data"])
        if data.ndim < 2:
            raise ValueError(f"Invalid semantic data shape: {data.shape}")
        height, width = data.shape[:2]
        if data.dtype == np.uint32:
            return data.reshape(height, width)
        if data.dtype == np.uint8 and data.ndim == 3 and data.shape[2] == 4:
            return np.ascontiguousarray(data).view(np.uint32).reshape(height, width)
        return data.astype(np.uint32, copy=False).reshape(height, width)

    @staticmethod
    def _id_to_labels(entry: dict[str, Any]) -> dict[Any, Any]:
        if "idToLabels" in entry:
            return entry["idToLabels"]
        info = entry.get("info", {})
        if isinstance(info, dict) and "idToLabels" in info:
            return info["idToLabels"]
        raise KeyError("semantic_segmentation output does not contain idToLabels")

    @staticmethod
    def _path(*parts: str) -> str:
        return str(PurePosixPath(*parts))

    @staticmethod
    def _safe_name(name: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "render_product"

    def write(self, data: dict[str, Any]) -> None:
        render_products = data.get("renderProducts")
        if not render_products:
            raise KeyError("Writer input does not contain renderProducts")
        multi = len(render_products) > 1
        frame_name = f"{self._frame_id:0{self._frame_padding}d}"
        for render_product_name, render_product_data in render_products.items():
            root = self._safe_name(render_product_name) if multi else ""
            semantic_entry = self._find(render_product_data, "semantic_segmentation")
            if not isinstance(semantic_entry, dict):
                raise KeyError(f"Missing semantic data for {render_product_name}")
            runtime_ids = self._runtime_id_image(semantic_entry)
            dataset_ids, diagnostics = self.mapping.remap(
                runtime_ids,
                self._id_to_labels(semantic_entry),
                strict=self._strict_mapping,
            )
            self.backend.schedule(
                F.write_np,
                data=dataset_ids,
                path=self._path(root, "semantic_id", f"semantic_id_{frame_name}.npy"),
            )
            self.backend.schedule(
                F.write_image,
                data=self.mapping.colorize(dataset_ids),
                path=self._path(root, "semantic_color", f"semantic_color_{frame_name}.png"),
            )
            if self._save_runtime_ids:
                self.backend.schedule(
                    F.write_np,
                    data=runtime_ids,
                    path=self._path(
                        root,
                        "semantic_runtime_id",
                        f"semantic_runtime_id_{frame_name}.npy",
                    ),
                )
            if self._save_rgb:
                rgb_entry = self._find(render_product_data, "rgb")
                if rgb_entry is None:
                    raise KeyError(f"Missing RGB data for {render_product_name}")
                self.backend.schedule(
                    F.write_image,
                    data=self._entry_data(rgb_entry),
                    path=self._path(root, "rgb", f"rgb_{frame_name}.png"),
                )
            self.backend.schedule(
                F.write_json,
                data={
                    "frame_id": self._frame_id,
                    "render_product": render_product_name,
                    "resolution": [int(runtime_ids.shape[1]), int(runtime_ids.shape[0])],
                    "runtime_id_mapping": diagnostics["runtime_id_mapping"],
                    "dataset_pixel_counts": diagnostics["dataset_pixel_counts"],
                    "unknown_labels": diagnostics["unknown_labels"],
                },
                path=self._path(root, "metadata", f"frame_{frame_name}.json"),
            )
        self._frame_id += 1
