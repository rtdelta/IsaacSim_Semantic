from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import FormatterConfig


@dataclass(frozen=True)
class FrameSource:
    frame_token: str
    frame_id: int
    directory: Path
    rgb: Path | None
    semantic_id: Path
    semantic_color: Path | None
    packet: Path | None


@dataclass(frozen=True)
class Artifact:
    source: Path
    destination: Path


@dataclass(frozen=True)
class ConversionSummary:
    source_root: str
    output_root: str
    frame_count: int
    variants: tuple[str, ...]
    semantic_shape: tuple[int, int]
    semantic_dtype: str
    artifact_count: int
    hardlink_count: int
    copy_count: int
    mapping_sha256: str


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc


def _discover_variant(
    root: Path,
    variant: str,
    *,
    require_rgb: bool,
    require_color: bool,
    require_packet: bool,
) -> dict[str, FrameSource]:
    directory = root / variant
    if not directory.is_dir():
        raise FileNotFoundError(f"v03 variant directory does not exist: {directory}")
    frames: dict[str, FrameSource] = {}
    with os.scandir(directory) as entries:
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False) or not entry.name.startswith("frame_"):
                continue
            token = entry.name[6:]
            if not token or not token.isdigit():
                raise ValueError(f"invalid v03 frame directory name: {entry.path}")
            if token in frames:
                raise ValueError(f"duplicate frame token {token!r} in {directory}")
            frame_directory = Path(entry.path)
            rgb = frame_directory / "rgb.png"
            semantic_id = frame_directory / "semantic_class_id.npy"
            semantic_color = frame_directory / "semantic_color.png"
            packet = frame_directory / "packet.json"
            required = [semantic_id]
            if require_rgb:
                required.append(rgb)
            if require_color:
                required.append(semantic_color)
            if require_packet:
                required.append(packet)
            missing = [path.name for path in required if not path.is_file()]
            if missing:
                raise FileNotFoundError(
                    f"v03 frame {frame_directory} is missing: {', '.join(missing)}"
                )
            frames[token] = FrameSource(
                frame_token=token,
                frame_id=int(token),
                directory=frame_directory,
                rgb=rgb if rgb.is_file() else None,
                semantic_id=semantic_id,
                semantic_color=semantic_color if semantic_color.is_file() else None,
                packet=packet if packet.is_file() else None,
            )
    if not frames:
        raise ValueError(f"no frame_* directories found in {directory}")
    return frames


def _summarize_frame_ids(values: Iterable[str], limit: int = 10) -> str:
    ordered = sorted(values, key=lambda item: int(item))
    visible = ", ".join(ordered[:limit])
    return visible + (f" (and {len(ordered) - limit} more)" if len(ordered) > limit else "")


def _validate_pairing(
    variants: dict[str, dict[str, FrameSource]],
    full_scene_variant: str,
    strict_pairing: bool,
) -> tuple[str, ...]:
    canonical = set(variants[full_scene_variant])
    if strict_pairing:
        failures: list[str] = []
        for variant, frames in variants.items():
            values = set(frames)
            missing = canonical - values
            extra = values - canonical
            if missing:
                failures.append(f"{variant} missing: {_summarize_frame_ids(missing)}")
            if extra:
                failures.append(f"{variant} extra: {_summarize_frame_ids(extra)}")
        if failures:
            raise ValueError("strict v03 frame pairing failed; " + "; ".join(failures))
        selected = canonical
    else:
        selected = set.intersection(*(set(value) for value in variants.values()))
        if not selected:
            raise ValueError("configured variants have no common frames")
    return tuple(sorted(selected, key=lambda item: int(item)))


def _validation_tokens(tokens: tuple[str, ...], level: str) -> tuple[str, ...]:
    if level == "full" or len(tokens) <= 3:
        return tokens
    return tuple(dict.fromkeys((tokens[0], tokens[len(tokens) // 2], tokens[-1])))


def _validate_payloads(
    variants: dict[str, dict[str, FrameSource]],
    tokens: tuple[str, ...],
    *,
    full_scene_variant: str,
    level: str,
) -> tuple[tuple[int, int], str]:
    import numpy as np
    from PIL import Image

    expected_shape: tuple[int, int] | None = None
    expected_dtype: str | None = None
    for token in _validation_tokens(tokens, level):
        for variant, frames in variants.items():
            frame = frames[token]
            array = np.load(frame.semantic_id, mmap_mode="r", allow_pickle=False)
            try:
                if array.ndim != 2:
                    raise ValueError(f"semantic array must be 2D: {frame.semantic_id}")
                if not np.issubdtype(array.dtype, np.integer):
                    raise ValueError(f"semantic array must use integer dtype: {frame.semantic_id}")
                shape = (int(array.shape[0]), int(array.shape[1]))
                dtype = str(array.dtype)
            finally:
                del array
            if expected_shape is None:
                expected_shape, expected_dtype = shape, dtype
            elif shape != expected_shape or dtype != expected_dtype:
                raise ValueError(
                    f"semantic contract mismatch at {frame.semantic_id}: "
                    f"shape={shape}, dtype={dtype}; expected shape={expected_shape}, "
                    f"dtype={expected_dtype}"
                )
            if frame.packet is not None:
                packet = _load_json(frame.packet)
                if not isinstance(packet, dict):
                    raise ValueError(f"packet must be a JSON object: {frame.packet}")
                if packet.get("frame_id") != frame.frame_id:
                    raise ValueError(f"packet frame_id mismatch: {frame.packet}")
                if packet.get("variant_id") != variant:
                    raise ValueError(f"packet variant_id mismatch: {frame.packet}")

        rgb = variants[full_scene_variant][token].rgb
        if rgb is None:
            raise FileNotFoundError(f"full-scene RGB is missing for frame {token}")
        with Image.open(rgb) as image:
            image.load() if level == "full" else image.verify()
            size = image.size
        if expected_shape != (size[1], size[0]):
            raise ValueError(
                f"RGB size {size} does not match semantic shape {expected_shape}: {rgb}"
            )
    assert expected_shape is not None and expected_dtype is not None
    return expected_shape, expected_dtype


def _normalize_mapping(path: Path, dataset_dtype: str) -> dict[str, Any]:
    raw = _load_json(path)
    entries = raw.get("classes") if isinstance(raw, dict) else raw
    if not isinstance(entries, list) or not entries:
        raise ValueError("semantic mapping must contain a non-empty classes list")
    normalized: list[dict[str, Any]] = []
    used_ids: set[int] = set()
    used_labels: set[str] = set()
    background: dict[str, Any] | None = None
    for index, value in enumerate(entries):
        if not isinstance(value, dict):
            raise ValueError(f"semantic mapping class {index} must be an object")
        class_id = value.get("id")
        label = value.get("label", value.get("name"))
        color = value.get("color", [0, 0, 0])
        if isinstance(class_id, bool) or not isinstance(class_id, int) or class_id < 0:
            raise ValueError(f"semantic mapping class {index}.id must be non-negative")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"semantic mapping class {index} needs label or name")
        label = label.strip()
        if not isinstance(color, list) or len(color) != 3 or any(
            isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 255
            for item in color
        ):
            raise ValueError(f"semantic mapping class {index}.color must be [r,g,b]")
        if class_id in used_ids or label in used_labels:
            raise ValueError(f"duplicate semantic class id or label at index {index}")
        used_ids.add(class_id)
        used_labels.add(label)
        item = {"id": class_id, "label": label, "color": color}
        if class_id == 0:
            background = item
        else:
            normalized.append(item)
    if background is None:
        background = {"id": 0, "label": "BACKGROUND", "color": [0, 0, 0]}
    return {
        "schema_version": 1,
        "semantic_type": "class",
        "dataset_dtype": dataset_dtype,
        "class_count": len(normalized),
        "background": background,
        "unknown": {
            "id": 65535,
            "label": "UNLABELLED",
            "color": [255, 0, 255],
            "policy": "error",
        },
        "classes": normalized,
    }


def _destination_roots(config: FormatterConfig) -> dict[str, dict[str, Path | None]]:
    result: dict[str, dict[str, Path | None]] = {
        config.contract.full_scene_variant: {
            "rgb": Path("full_scene_rgb"),
            "semantic": Path("full_scene_semantic"),
            "metadata": Path("metadata/full_scene"),
        },
        config.contract.reference_variant: {
            "rgb": None,
            "semantic": Path("teeth_only_semantic"),
            "metadata": Path("metadata/front_teeth_only"),
        },
    }
    for variant in config.contract.additional_variants:
        result[variant] = {
            "rgb": Path(f"{variant}_rgb"),
            "semantic": Path(f"{variant}_semantic"),
            "metadata": Path(f"metadata/{variant}"),
        }
    return result


def _artifacts(
    config: FormatterConfig,
    variants: dict[str, dict[str, FrameSource]],
    tokens: tuple[str, ...],
) -> list[Artifact]:
    roots = _destination_roots(config)
    artifacts: list[Artifact] = []
    for variant, frames in variants.items():
        destinations = roots[variant]
        for token in tokens:
            frame = frames[token]
            semantic_root = destinations["semantic"]
            assert semantic_root is not None
            artifacts.append(
                Artifact(
                    frame.semantic_id,
                    semantic_root / "semantic_id" / f"semantic_id_{token}.npy",
                )
            )
            if config.contract.include_semantic_color:
                assert frame.semantic_color is not None
                artifacts.append(
                    Artifact(
                        frame.semantic_color,
                        semantic_root / "semantic_color" / f"semantic_color_{token}.png",
                    )
                )
            rgb_root = destinations["rgb"]
            if frame.rgb is not None and rgb_root is not None:
                artifacts.append(Artifact(frame.rgb, rgb_root / f"rgb_{token}.png"))
            if config.contract.include_packet_metadata:
                assert frame.packet is not None
                metadata_root = destinations["metadata"]
                assert metadata_root is not None
                artifacts.append(Artifact(frame.packet, metadata_root / f"frame_{token}.json"))
    destinations = [item.destination for item in artifacts]
    if len(destinations) != len(set(destinations)):
        raise ValueError("internal output mapping produced duplicate destination paths")
    return artifacts


def _materialize_one(source: Path, destination: Path, mode: str) -> str:
    if mode in {"hardlink", "hardlink_or_copy"}:
        try:
            os.link(source, destination)
            return "hardlink"
        except OSError as exc:
            if mode == "hardlink" or exc.errno not in {
                errno.EXDEV,
                errno.EPERM,
                errno.EACCES,
                errno.ENOTSUP,
            }:
                raise
    shutil.copy2(source, destination)
    return "copy"


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def convert_dataset(config: FormatterConfig) -> ConversionSummary:
    if not config.source_root.is_dir():
        raise FileNotFoundError(f"source_root does not exist: {config.source_root}")
    if not config.semantic_mapping.is_file():
        raise FileNotFoundError(f"semantic_mapping does not exist: {config.semantic_mapping}")
    if config.output_root.exists():
        raise FileExistsError(f"output_root already exists: {config.output_root}")

    variant_names = (
        config.contract.full_scene_variant,
        config.contract.reference_variant,
        *config.contract.additional_variants,
    )
    variants: dict[str, dict[str, FrameSource]] = {}
    for variant in variant_names:
        variants[variant] = _discover_variant(
            config.source_root,
            variant,
            require_rgb=variant == config.contract.full_scene_variant,
            require_color=config.contract.include_semantic_color,
            require_packet=config.contract.include_packet_metadata,
        )
    tokens = _validate_pairing(
        variants,
        config.contract.full_scene_variant,
        config.contract.strict_pairing,
    )
    shape, dtype = _validate_payloads(
        variants,
        tokens,
        full_scene_variant=config.contract.full_scene_variant,
        level=config.validation.level,
    )
    mapping = _normalize_mapping(config.semantic_mapping, dtype)
    artifacts = _artifacts(config, variants, tokens)

    config.output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = config.output_root.parent / (
        f".{config.output_root.name}.staging-{uuid.uuid4().hex}"
    )
    staging.mkdir(parents=False, exist_ok=False)
    try:
        for parent in {item.destination.parent for item in artifacts}:
            (staging / parent).mkdir(parents=True, exist_ok=True)

        def materialize(item: Artifact) -> str:
            return _materialize_one(
                item.source,
                staging / item.destination,
                config.materialization.mode,
            )

        with ThreadPoolExecutor(max_workers=config.materialization.workers) as executor:
            operation_counts = Counter(executor.map(materialize, artifacts))

        mapping_path = staging / "semantic_mapping.json"
        _write_json(mapping_path, mapping)
        mapping_sha256 = hashlib.sha256(mapping_path.read_bytes()).hexdigest()
        input_fragment = {
            "full_scene": {
                "rgb_dir": str(config.output_root / "full_scene_rgb"),
                "semantic_dir": str(
                    config.output_root / "full_scene_semantic/semantic_id"
                ),
            },
            "reference": {
                "capture_variant": "front_teeth_only",
                "semantic_dir": str(
                    config.output_root / "teeth_only_semantic/semantic_id"
                ),
            },
            "semantic_mapping": str(config.output_root / "semantic_mapping.json"),
        }
        _write_json(staging / "postprocess_v02_inputs.json", input_fragment)

        summary = ConversionSummary(
            source_root=str(config.source_root),
            output_root=str(config.output_root),
            frame_count=len(tokens),
            variants=variant_names,
            semantic_shape=shape,
            semantic_dtype=dtype,
            artifact_count=len(artifacts),
            hardlink_count=operation_counts["hardlink"],
            copy_count=operation_counts["copy"],
            mapping_sha256=mapping_sha256,
        )
        manifest = {
            "schema_version": 1,
            "formatter": "260821_01Formatter_Capture_PostProcess",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "config": str(config.config_path),
            **asdict(summary),
        }
        _write_json(staging / "conversion_manifest.json", manifest)
        os.replace(staging, config.output_root)
        return summary
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

