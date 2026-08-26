from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


def _object(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return value


def _reject_unknown(value: Mapping[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"{context} contains unknown keys: {', '.join(unknown)}")


def _string(value: Mapping[str, Any], key: str, context: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return result.strip()


def _resolve(base: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve()


@dataclass(frozen=True)
class ContractConfig:
    full_scene_variant: str
    reference_variant: str
    additional_variants: tuple[str, ...]
    strict_pairing: bool
    include_semantic_color: bool
    include_packet_metadata: bool


@dataclass(frozen=True)
class MaterializationConfig:
    mode: str
    workers: int


@dataclass(frozen=True)
class ValidationConfig:
    level: str


@dataclass(frozen=True)
class FormatterConfig:
    config_path: Path
    source_root: Path
    output_root: Path
    semantic_mapping: Path
    contract: ContractConfig
    materialization: MaterializationConfig
    validation: ValidationConfig


def load_config(path: str | Path) -> FormatterConfig:
    config_path = Path(path).expanduser().resolve()
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read config {config_path}: {exc}") from exc
    raw = _object(raw, "config")
    _reject_unknown(
        raw,
        {
            "schema_version",
            "source_root",
            "output_root",
            "semantic_mapping",
            "contract",
            "materialization",
            "validation",
        },
        "config",
    )
    if raw.get("schema_version") != 1:
        raise ValueError("config.schema_version must be 1")
    base = config_path.parent

    contract_raw = _object(raw.get("contract"), "config.contract")
    _reject_unknown(
        contract_raw,
        {
            "full_scene_variant",
            "reference_variant",
            "additional_variants",
            "strict_pairing",
            "include_semantic_color",
            "include_packet_metadata",
        },
        "config.contract",
    )
    additional = contract_raw.get("additional_variants", [])
    if not isinstance(additional, list) or any(
        not isinstance(item, str) or not item.strip() for item in additional
    ):
        raise ValueError("config.contract.additional_variants must be an array of strings")
    full_scene = _string(contract_raw, "full_scene_variant", "config.contract")
    reference = _string(contract_raw, "reference_variant", "config.contract")
    if reference != "front_teeth_only":
        raise ValueError(
            "config.contract.reference_variant must be front_teeth_only for "
            "Post Process Chain v02"
        )
    additional_variants = tuple(item.strip() for item in additional)
    all_variants = (full_scene, reference, *additional_variants)
    if len(set(all_variants)) != len(all_variants):
        raise ValueError("configured variant names must be unique")
    for key in ("strict_pairing", "include_semantic_color", "include_packet_metadata"):
        if not isinstance(contract_raw.get(key), bool):
            raise ValueError(f"config.contract.{key} must be boolean")

    materialization_raw = _object(
        raw.get("materialization"), "config.materialization"
    )
    _reject_unknown(materialization_raw, {"mode", "workers"}, "config.materialization")
    mode = _string(materialization_raw, "mode", "config.materialization")
    if mode not in {"hardlink", "hardlink_or_copy", "copy"}:
        raise ValueError(
            "config.materialization.mode must be hardlink, hardlink_or_copy, or copy"
        )
    workers = materialization_raw.get("workers")
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise ValueError("config.materialization.workers must be a positive integer")

    validation_raw = _object(raw.get("validation"), "config.validation")
    _reject_unknown(validation_raw, {"level"}, "config.validation")
    level = _string(validation_raw, "level", "config.validation")
    if level not in {"sample", "full"}:
        raise ValueError("config.validation.level must be sample or full")

    source_root = _resolve(base, _string(raw, "source_root", "config"))
    output_root = _resolve(base, _string(raw, "output_root", "config"))
    semantic_mapping = _resolve(base, _string(raw, "semantic_mapping", "config"))
    if (
        source_root == output_root
        or source_root in output_root.parents
        or output_root in source_root.parents
    ):
        raise ValueError("source_root and output_root must not equal or contain each other")

    return FormatterConfig(
        config_path=config_path,
        source_root=source_root,
        output_root=output_root,
        semantic_mapping=semantic_mapping,
        contract=ContractConfig(
            full_scene_variant=full_scene,
            reference_variant=reference,
            additional_variants=additional_variants,
            strict_pairing=contract_raw["strict_pairing"],
            include_semantic_color=contract_raw["include_semantic_color"],
            include_packet_metadata=contract_raw["include_packet_metadata"],
        ),
        materialization=MaterializationConfig(mode=mode, workers=workers),
        validation=ValidationConfig(level=level),
    )
