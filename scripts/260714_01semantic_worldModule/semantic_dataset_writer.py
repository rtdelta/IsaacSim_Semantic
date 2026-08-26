"""Replicator Writer with probe validation and frame-transaction output."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Iterable

import numpy as np
from omni.replicator.core import AnnotatorRegistry, Writer
from omni.replicator.core import functional as F

from capture_context import (
    CaptureContext,
    CaptureLedger,
    CaptureOperation,
    CaptureReceipt,
    CaptureVariant,
    ProbeReceipt,
)
from capture_launch_config import (
    ImageOutputFolders,
    VariantValidationConfig,
)
from frame_transaction import FrameStagingTransaction
from semantic_content_validation import validate_semantic_content
from semantic_mapping import SemanticMapping


class SemanticDatasetWriter(Writer):
    version = "5.0.0"

    def __init__(
        self,
        backend: Any,
        semantic_schema: str,
        rgb: bool = True,
        save_runtime_ids: bool = False,
        strict_mapping: bool = True,
        frame_padding: int = 4,
        output_folders: ImageOutputFolders | None = None,
        transparent_isolated_background: bool = False,
        save_front_teeth_only_rgb: bool = False,
        variant_validation: VariantValidationConfig | None = None,
        overwrite_output: bool = False,
    ) -> None:
        self.data_structure = "renderProduct"
        self.backend = backend
        self._backend = backend
        self.mapping = SemanticMapping(semantic_schema)
        self._frame_padding = frame_padding
        self._save_rgb = rgb
        self._save_runtime_ids = save_runtime_ids
        self._strict_mapping = strict_mapping
        self._output_folders = output_folders or ImageOutputFolders(
            full_scene_rgb="full_scene_excavator_rgb",
            full_scene_semantic="full_scene_excavator_semantic",
            excavator_only_rgb="excavator_only_rgb",
            excavator_only_semantic="excavator_only_semantic",
            front_teeth_only_rgb="front_teeth_only_rgb",
            front_teeth_only_semantic="front_teeth_only_semantic",
        )
        self._transparent_isolated_background = bool(transparent_isolated_background)
        self._save_front_teeth_only_rgb = bool(save_front_teeth_only_rgb)
        self._variant_validation = (
            variant_validation or VariantValidationConfig.default()
        )
        self._ledger = CaptureLedger()
        self._frame_transaction = FrameStagingTransaction(
            str(self._backend.output_dir),
            frame_padding=self._frame_padding,
            allow_overwrite=overwrite_output,
        )
        self.version = type(self).version
        self._validate_configured_labels()

        self.annotators = []
        if rgb:
            self.annotators.append(AnnotatorRegistry.get_annotator("rgb"))
        if self._transparent_isolated_background:
            self.annotators.append(
                AnnotatorRegistry.get_annotator("distance_to_camera")
            )
        self.annotators.append(
            AnnotatorRegistry.get_annotator(
                "semantic_segmentation",
                init_params={"colorize": False, "semanticFilter": "class:*"},
            )
        )
        self.backend.schedule(
            F.write_json,
            data=self.mapping.schema,
            path="semantic_mapping.json",
        )

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
        return np.asarray(
            entry["data"] if isinstance(entry, dict) and "data" in entry else entry
        )

    @classmethod
    def _rgb_image(cls, entry: Any, expected_shape: tuple[int, int]) -> np.ndarray:
        data = cls._entry_data(entry)
        if data.dtype != np.uint8:
            raise ValueError(f"RGB data must be uint8, got {data.dtype}")
        if data.ndim != 3 or data.shape[2] not in {3, 4}:
            raise ValueError(f"RGB data must be HxWx3 or HxWx4, got {data.shape}")
        if data.shape[:2] != expected_shape:
            raise ValueError(
                f"RGB and semantic resolution differ: {data.shape[:2]} != {expected_shape}"
            )
        return np.ascontiguousarray(data)

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

    @classmethod
    def _isolated_rgba(
        cls,
        rgb: np.ndarray,
        depth_entry: Any,
        expected_shape: tuple[int, int],
    ) -> np.ndarray:
        depth = cls._entry_data(depth_entry).astype(np.float32, copy=False)
        if depth.ndim == 3 and depth.shape[2] == 1:
            depth = depth[:, :, 0]
        if depth.shape != expected_shape:
            raise ValueError(
                f"RGB and isolated depth resolution differ: "
                f"{depth.shape} != {expected_shape}"
            )
        geometry_mask = np.isfinite(depth) & (depth > 0.0)
        if rgb.shape[2] == 3:
            rgba = np.empty((*expected_shape, 4), dtype=np.uint8)
            rgba[:, :, :3] = rgb
        else:
            rgba = np.array(rgb, copy=True)
        rgba[:, :, 3] = np.where(geometry_mask, 255, 0).astype(np.uint8)
        return np.ascontiguousarray(rgba)

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

    def _validate_configured_labels(self) -> None:
        if not self._variant_validation.enabled:
            return
        known = {
            label.casefold()
            for dataset_id, label in self.mapping.id_to_label.items()
            if dataset_id not in {self.mapping.background_id, self.mapping.unknown_id}
        }
        errors: list[str] = []
        for variant in CaptureVariant:
            rule = self._variant_validation.rule_for(variant.value)
            configured = {
                label.casefold()
                for labels in (
                    rule.allowed_labels or (),
                    rule.required_any_labels,
                    rule.forbidden_labels,
                )
                for label in labels
            }
            unknown = sorted(configured - known)
            if unknown:
                errors.append(f"{variant.value}: {', '.join(unknown)}")
        if errors:
            raise ValueError(
                "Variant validation labels are absent from the semantic mapping: "
                + "; ".join(errors)
            )

    def arm_render(self, context: CaptureContext) -> None:
        self._ledger.arm(context)

    def arm_capture(self, context: CaptureContext) -> None:
        if context.operation is not CaptureOperation.CAPTURE:
            raise ValueError("arm_capture expects a CAPTURE context")
        self.arm_render(context)

    def require_completed(
        self,
        frame_id: int,
        variant: CaptureVariant = CaptureVariant.FULL_SCENE,
    ) -> CaptureReceipt:
        return self._ledger.require_completed(frame_id, variant)

    def require_probe_completed(self, context: CaptureContext) -> ProbeReceipt:
        return self._ledger.require_probe_completed(context)

    @property
    def pending_count(self) -> int:
        return self._ledger.pending_count

    @property
    def completed_count(self) -> int:
        return self._ledger.completed_count

    @property
    def completed_probe_count(self) -> int:
        return self._ledger.completed_probe_count

    @property
    def completed_by_variant(self) -> dict[str, int]:
        return self._ledger.completed_by_variant

    @property
    def committed_frame_count(self) -> int:
        return self._frame_transaction.committed_frame_count

    def _variant_roots(self, variant: CaptureVariant) -> tuple[str, str]:
        if variant is CaptureVariant.FULL_SCENE:
            return (
                self._output_folders.full_scene_rgb,
                self._output_folders.full_scene_semantic,
            )
        if variant is CaptureVariant.EXCAVATOR_ONLY:
            return (
                self._output_folders.excavator_only_rgb,
                self._output_folders.excavator_only_semantic,
            )
        if variant is CaptureVariant.FRONT_TEETH_ONLY:
            return (
                self._output_folders.front_teeth_only_rgb,
                self._output_folders.front_teeth_only_semantic,
            )
        raise ValueError(f"Unsupported capture variant: {variant!r}")

    def _should_save_rgb(self, variant: CaptureVariant) -> bool:
        if not self._save_rgb:
            return False
        if variant is CaptureVariant.FRONT_TEETH_ONLY:
            return self._save_front_teeth_only_rgb
        return True

    def _staging_prefix(self, frame_id: int) -> str:
        return self._frame_transaction.staging_prefix(frame_id)

    def _staged_path(self, frame_id: int, final_path: str) -> str:
        return self._frame_transaction.staged_path(frame_id, final_path)

    def wait_until_done(self) -> None:
        self._backend.wait_until_done()

    def commit_frame(
        self,
        frame_id: int,
        receipts: Iterable[CaptureReceipt],
    ) -> None:
        self.wait_until_done()
        self._frame_transaction.commit(frame_id, receipts)

    def discard_frame(self, frame_id: int) -> None:
        self.wait_until_done()
        self._frame_transaction.discard(frame_id)

    def write(self, data: dict[str, Any]) -> None:
        render_products = data.get("renderProducts")
        if not render_products:
            raise KeyError("Writer input does not contain renderProducts")
        if len(render_products) != 1:
            raise RuntimeError(
                f"SemanticDatasetWriter expects exactly one RenderProduct, got {len(render_products)}"
            )

        context = self._ledger.consume()
        render_product_name, render_product_data = next(iter(render_products.items()))
        semantic_entry = self._find(render_product_data, "semantic_segmentation")
        if not isinstance(semantic_entry, dict):
            raise KeyError(f"Missing semantic data for {render_product_name}")
        runtime_ids = self._runtime_id_image(semantic_entry)
        dataset_ids, diagnostics = self.mapping.remap(
            runtime_ids,
            self._id_to_labels(semantic_entry),
            strict=self._strict_mapping,
        )
        semantic_validation = validate_semantic_content(
            config=self._variant_validation,
            variant=context.variant,
            dataset_ids=dataset_ids,
            id_to_label=self.mapping.id_to_label,
            background_id=self.mapping.background_id,
        )
        present_ids = semantic_validation.dataset_ids_present
        present_labels = semantic_validation.labels_present
        validation_errors = semantic_validation.errors

        if context.operation is CaptureOperation.PROBE:
            self._ledger.complete_probe(
                ProbeReceipt(
                    frame_id=context.frame_id,
                    variant=context.variant,
                    visibility_generation=context.visibility_generation,
                    attempt=context.attempt,
                    probe_index=context.probe_index,
                    resolution=(int(runtime_ids.shape[1]), int(runtime_ids.shape[0])),
                    semantic_labels_present=present_labels,
                    semantic_dataset_ids_present=present_ids,
                    validation_passed=not validation_errors,
                    validation_errors=validation_errors,
                )
            )
            return

        if validation_errors:
            raise RuntimeError(
                f"Formal capture validation failed for frame {context.frame_id}/"
                f"{context.variant.value}/g{context.visibility_generation}: "
                + "; ".join(validation_errors)
            )

        frame_name = f"{context.frame_id:0{self._frame_padding}d}"
        rgb_root, semantic_root = self._variant_roots(context.variant)
        staged_files: list[tuple[str, str]] = []

        semantic_id_path = self._path(
            semantic_root,
            "semantic_id",
            f"semantic_id_{frame_name}.npy",
        )
        staged_semantic_id_path = self._staged_path(
            context.frame_id,
            semantic_id_path,
        )
        self.backend.schedule(F.write_np, data=dataset_ids, path=staged_semantic_id_path)
        staged_files.append((staged_semantic_id_path, semantic_id_path))

        semantic_color_path = self._path(
            semantic_root,
            "semantic_color",
            f"semantic_color_{frame_name}.png",
        )
        staged_semantic_color_path = self._staged_path(
            context.frame_id,
            semantic_color_path,
        )
        self.backend.schedule(
            F.write_image,
            data=self.mapping.colorize(dataset_ids),
            path=staged_semantic_color_path,
        )
        staged_files.append((staged_semantic_color_path, semantic_color_path))

        runtime_id_path = None
        if self._save_runtime_ids:
            runtime_id_path = self._path(
                semantic_root,
                "semantic_runtime_id",
                f"semantic_runtime_id_{frame_name}.npy",
            )
            staged_runtime_id_path = self._staged_path(
                context.frame_id,
                runtime_id_path,
            )
            self.backend.schedule(
                F.write_np,
                data=runtime_ids,
                path=staged_runtime_id_path,
            )
            staged_files.append((staged_runtime_id_path, runtime_id_path))

        rgb_path = None
        if self._should_save_rgb(context.variant):
            rgb_entry = self._find(render_product_data, "rgb")
            if rgb_entry is None:
                raise KeyError(f"Missing RGB data for {render_product_name}")
            rgb_data = self._rgb_image(rgb_entry, runtime_ids.shape)
            if (
                context.variant is not CaptureVariant.FULL_SCENE
                and self._transparent_isolated_background
            ):
                depth_entry = self._find(render_product_data, "distance_to_camera")
                if depth_entry is None:
                    raise KeyError(
                        f"Missing isolated-render depth data for {render_product_name}"
                    )
                rgb_data = self._isolated_rgba(
                    rgb_data,
                    depth_entry,
                    runtime_ids.shape,
                )
            rgb_path = self._path(rgb_root, f"rgb_{frame_name}.png")
            staged_rgb_path = self._staged_path(context.frame_id, rgb_path)
            self.backend.schedule(F.write_image, data=rgb_data, path=staged_rgb_path)
            staged_files.append((staged_rgb_path, rgb_path))

        metadata_path = self._path(
            "metadata",
            context.variant.value,
            f"frame_{frame_name}.json",
        )
        staged_metadata_path = self._staged_path(context.frame_id, metadata_path)
        metadata = {
            "schema_version": 5,
            **context.to_dict(),
            "render_product": render_product_name,
            "resolution": [int(runtime_ids.shape[1]), int(runtime_ids.shape[0])],
            "runtime_id_mapping": diagnostics["runtime_id_mapping"],
            "dataset_pixel_counts": diagnostics["dataset_pixel_counts"],
            "unknown_labels": diagnostics["unknown_labels"],
            "semantic_labels_present": list(present_labels),
            "semantic_dataset_ids_present": list(present_ids),
            "validation_passed": True,
            "validation_errors": [],
            "background_alpha": (
                "isolated_render_depth"
                if context.variant is not CaptureVariant.FULL_SCENE
                and self._should_save_rgb(context.variant)
                and self._transparent_isolated_background
                else "source_rgb"
            ),
        }
        self.backend.schedule(
            F.write_json,
            data=metadata,
            path=staged_metadata_path,
        )
        staged_files.append((staged_metadata_path, metadata_path))

        self._ledger.complete(
            CaptureReceipt(
                frame_id=context.frame_id,
                rgb_path=rgb_path,
                semantic_id_path=semantic_id_path,
                semantic_color_path=semantic_color_path,
                runtime_id_path=runtime_id_path,
                metadata_path=metadata_path,
                variant=context.variant,
                visibility_generation=context.visibility_generation,
                semantic_labels_present=present_labels,
                validation_passed=True,
                validation_errors=(),
                staged_files=tuple(staged_files),
                settle_attempts_before_capture=(
                    context.settle_attempts_before_capture
                ),
            )
        )
