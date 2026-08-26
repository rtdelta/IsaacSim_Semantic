from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple


def _load_object(path: Path, description: str) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise ValueError(f"cannot read {description}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {description}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{description} must contain a JSON object")
    return value


def _reject_unknown(
    value: Mapping[str, Any],
    allowed: set[str],
    context: str,
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"{context} contains unknown fields: {', '.join(unknown)}")


def _object(value: Mapping[str, Any], key: str, context: str) -> Dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ValueError(f"{context}.{key} must be an object")
    return item


def _string(value: Mapping[str, Any], key: str, context: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return item.strip()


def _integer(
    value: Mapping[str, Any],
    key: str,
    default: int,
    context: str,
    minimum: int = 1,
) -> int:
    item = value.get(key, default)
    if isinstance(item, bool) or not isinstance(item, int) or item < minimum:
        raise ValueError(f"{context}.{key} must be an integer >= {minimum}")
    return item


def _boolean(
    value: Mapping[str, Any],
    key: str,
    default: bool,
    context: str,
) -> bool:
    item = value.get(key, default)
    if not isinstance(item, bool):
        raise ValueError(f"{context}.{key} must be a boolean")
    return item


def _resolve(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


@dataclass(frozen=True)
class InputsConfig:
    whole_scene_semantic_dir: Path
    excavator_only_semantic_dir: Path
    semantic_mapping: Path


@dataclass(frozen=True)
class TargetsConfig:
    labels: Tuple[str, ...]
    group_name: str


@dataclass(frozen=True)
class RatioConfig:
    numerator: str
    denominator: str
    zero_denominator: str
    over_one: str


@dataclass(frozen=True)
class ExecutionConfig:
    backend: str
    batch_frames: int
    reader_threads: int
    ring_slots: int
    cpu_workers: int
    device: str
    on_frame_error: str
    verify_sample_frames: int


@dataclass(frozen=True)
class OutputConfig:
    root: Path
    overwrite: bool
    resume: bool
    write_counts_cache: bool


@dataclass(frozen=True)
class RunConfig:
    config_path: Path
    inputs: InputsConfig
    targets: TargetsConfig
    ratio: RatioConfig
    execution: ExecutionConfig
    output: OutputConfig


def load_config(path: Path) -> RunConfig:
    path = path.resolve()
    raw = _load_object(path, "run config")
    _reject_unknown(
        raw,
        {
            "schema_version",
            "inputs",
            "targets",
            "ratio",
            "pairing",
            "execution",
            "output",
        },
        "config",
    )
    if raw.get("schema_version") != 1:
        raise ValueError("config.schema_version must be 1")
    base = path.parent

    inputs_raw = _object(raw, "inputs", "config")
    _reject_unknown(
        inputs_raw,
        {
            "whole_scene_semantic_dir",
            "excavator_only_semantic_dir",
            "semantic_mapping",
        },
        "config.inputs",
    )
    inputs = InputsConfig(
        whole_scene_semantic_dir=_resolve(
            base,
            _string(
                inputs_raw,
                "whole_scene_semantic_dir",
                "config.inputs",
            ),
        ),
        excavator_only_semantic_dir=_resolve(
            base,
            _string(
                inputs_raw,
                "excavator_only_semantic_dir",
                "config.inputs",
            ),
        ),
        semantic_mapping=_resolve(
            base,
            _string(inputs_raw, "semantic_mapping", "config.inputs"),
        ),
    )
    for directory, description in (
        (inputs.whole_scene_semantic_dir, "whole-scene semantic directory"),
        (inputs.excavator_only_semantic_dir, "excavator-only semantic directory"),
    ):
        if not directory.is_dir():
            raise FileNotFoundError(f"{description} does not exist: {directory}")
    if not inputs.semantic_mapping.is_file():
        raise FileNotFoundError(
            f"semantic mapping does not exist: {inputs.semantic_mapping}"
        )

    targets_raw = _object(raw, "targets", "config")
    _reject_unknown(targets_raw, {"labels", "group_name"}, "config.targets")
    labels_value = targets_raw.get("labels")
    if (
        not isinstance(labels_value, list)
        or len(labels_value) != 5
        or not all(isinstance(item, str) and item.strip() for item in labels_value)
    ):
        raise ValueError("config.targets.labels must contain exactly five strings")
    labels = tuple(item.strip() for item in labels_value)
    if len(set(labels)) != 5:
        raise ValueError("config.targets.labels must not contain duplicates")
    targets = TargetsConfig(
        labels=labels,
        group_name=_string(targets_raw, "group_name", "config.targets"),
    )
    if targets.group_name in labels:
        raise ValueError("config.targets.group_name must differ from target labels")

    ratio_raw = _object(raw, "ratio", "config")
    _reject_unknown(
        ratio_raw,
        {"numerator", "denominator", "zero_denominator", "over_one"},
        "config.ratio",
    )
    ratio = RatioConfig(
        numerator=_string(ratio_raw, "numerator", "config.ratio"),
        denominator=_string(ratio_raw, "denominator", "config.ratio"),
        zero_denominator=_string(
            ratio_raw,
            "zero_denominator",
            "config.ratio",
        ),
        over_one=_string(ratio_raw, "over_one", "config.ratio"),
    )
    if ratio.numerator != "whole_scene" or ratio.denominator != "excavator_only":
        raise ValueError(
            "ratio direction must be whole_scene / excavator_only"
        )
    if ratio.zero_denominator != "null":
        raise ValueError("config.ratio.zero_denominator must be 'null'")
    if ratio.over_one != "keep_and_flag":
        raise ValueError("config.ratio.over_one must be 'keep_and_flag'")

    pairing_raw = _object(raw, "pairing", "config")
    _reject_unknown(pairing_raw, {"mode"}, "config.pairing")
    if _string(pairing_raw, "mode", "config.pairing") != "strict":
        raise ValueError("config.pairing.mode must be 'strict'")

    execution_raw = _object(raw, "execution", "config")
    _reject_unknown(
        execution_raw,
        {
            "backend",
            "batch_frames",
            "reader_threads",
            "ring_slots",
            "cpu_workers",
            "device",
            "on_frame_error",
            "verify_sample_frames",
        },
        "config.execution",
    )
    backend = _string(execution_raw, "backend", "config.execution")
    if backend not in {"auto", "numpy", "torch_cuda", "triton_cuda"}:
        raise ValueError(
            "config.execution.backend must be auto, numpy, torch_cuda, or triton_cuda"
        )
    on_frame_error = _string(
        execution_raw,
        "on_frame_error",
        "config.execution",
    )
    if on_frame_error != "fail_fast":
        raise ValueError("only fail_fast frame error handling is supported")
    default_cpu_workers = min(os.cpu_count() or 1, 16)
    execution = ExecutionConfig(
        backend=backend,
        batch_frames=_integer(
            execution_raw,
            "batch_frames",
            128,
            "config.execution",
        ),
        reader_threads=_integer(
            execution_raw,
            "reader_threads",
            8,
            "config.execution",
        ),
        ring_slots=_integer(
            execution_raw,
            "ring_slots",
            3,
            "config.execution",
            minimum=2,
        ),
        cpu_workers=_integer(
            execution_raw,
            "cpu_workers",
            default_cpu_workers,
            "config.execution",
        ),
        device=str(execution_raw.get("device", "cuda")).strip() or "cuda",
        on_frame_error=on_frame_error,
        verify_sample_frames=_integer(
            execution_raw,
            "verify_sample_frames",
            8,
            "config.execution",
            minimum=0,
        ),
    )

    output_raw = _object(raw, "output", "config")
    _reject_unknown(
        output_raw,
        {"root", "overwrite", "resume", "write_counts_cache"},
        "config.output",
    )
    output = OutputConfig(
        root=_resolve(base, _string(output_raw, "root", "config.output")),
        overwrite=_boolean(output_raw, "overwrite", False, "config.output"),
        resume=_boolean(output_raw, "resume", True, "config.output"),
        write_counts_cache=_boolean(
            output_raw,
            "write_counts_cache",
            True,
            "config.output",
        ),
    )
    if output.overwrite and output.resume:
        raise ValueError("config.output.overwrite and resume cannot both be true")
    for input_path in (
        inputs.whole_scene_semantic_dir,
        inputs.excavator_only_semantic_dir,
    ):
        if (
            output.root == input_path
            or input_path in output.root.parents
            or output.root in input_path.parents
        ):
            raise ValueError(
                "output root must not equal, contain, or be contained by an input directory"
            )

    return RunConfig(
        config_path=path,
        inputs=inputs,
        targets=targets,
        ratio=ratio,
        execution=execution,
        output=output,
    )


__all__ = [
    "ExecutionConfig",
    "InputsConfig",
    "OutputConfig",
    "RatioConfig",
    "RunConfig",
    "TargetsConfig",
    "load_config",
]

