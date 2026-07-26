from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..common.config_io import (
    load_json_object,
    optional_boolean,
    optional_integer,
    optional_string,
    reject_unknown_fields,
    require_list,
    require_object,
    require_string,
    resolve_path,
)


@dataclass(frozen=True)
class InputConfig:
    rgb_dir: Path
    semantic_dir: Path
    semantic_mapping: Path


@dataclass(frozen=True)
class ExecutionConfig:
    workers: int
    max_in_flight: int
    overwrite: bool
    on_frame_error: str


@dataclass(frozen=True)
class OutputConfig:
    image_mode: str
    write_manifest: bool


@dataclass(frozen=True)
class ModuleSpec:
    module_id: str
    module_type: str
    enabled: bool
    config_path: Path
    depends_on: Tuple[str, ...]


@dataclass(frozen=True)
class OrchestratorConfig:
    config_path: Path
    inputs: InputConfig
    output_root: Path
    execution: ExecutionConfig
    output: OutputConfig
    modules: Tuple[ModuleSpec, ...]

    @property
    def enabled_modules(self) -> Tuple[ModuleSpec, ...]:
        return tuple(item for item in self.modules if item.enabled)

    def ordered_modules(self) -> Tuple[ModuleSpec, ...]:
        enabled = self.enabled_modules
        by_id = {item.module_id: item for item in enabled}
        indegree = {item.module_id: 0 for item in enabled}
        dependents: Dict[str, List[str]] = {item.module_id: [] for item in enabled}
        position = {item.module_id: index for index, item in enumerate(enabled)}

        for item in enabled:
            for dependency in item.depends_on:
                indegree[item.module_id] += 1
                dependents[dependency].append(item.module_id)

        ready = sorted(
            (module_id for module_id, degree in indegree.items() if degree == 0),
            key=position.get,
        )
        ordered = []
        while ready:
            module_id = ready.pop(0)
            ordered.append(by_id[module_id])
            for dependent in dependents[module_id]:
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    ready.append(dependent)
                    ready.sort(key=position.get)

        if len(ordered) != len(enabled):
            cyclic = sorted(
                module_id for module_id, degree in indegree.items() if degree > 0
            )
            raise ValueError(
                f"module dependencies contain a cycle: {', '.join(cyclic)}"
            )
        return tuple(ordered)


def _validate_input_output_separation(config: OrchestratorConfig) -> None:
    for input_dir, description in (
        (config.inputs.rgb_dir, "RGB"),
        (config.inputs.semantic_dir, "semantic"),
    ):
        output_root = config.output_root
        if (
            output_root == input_dir
            or input_dir in output_root.parents
            or output_root in input_dir.parents
        ):
            raise ValueError(
                f"output_root must not equal, contain, or be contained by {description} directory"
            )


def load_orchestrator_config(path: Path) -> OrchestratorConfig:
    path = path.resolve()
    raw = load_json_object(path, "orchestrator config")
    context = "orchestrator"
    reject_unknown_fields(
        raw,
        {
            "schema_version",
            "inputs",
            "output_root",
            "execution",
            "output",
            "modules",
        },
        context,
    )
    if raw.get("schema_version") != 1:
        raise ValueError("orchestrator.schema_version must be 1")

    base_directory = path.parent
    inputs_raw = require_object(raw, "inputs", context)
    reject_unknown_fields(
        inputs_raw,
        {"rgb_dir", "semantic_dir", "semantic_mapping"},
        "orchestrator.inputs",
    )
    inputs = InputConfig(
        rgb_dir=resolve_path(
            require_string(inputs_raw, "rgb_dir", "orchestrator.inputs"),
            base_directory,
        ),
        semantic_dir=resolve_path(
            require_string(inputs_raw, "semantic_dir", "orchestrator.inputs"),
            base_directory,
        ),
        semantic_mapping=resolve_path(
            require_string(
                inputs_raw,
                "semantic_mapping",
                "orchestrator.inputs",
            ),
            base_directory,
        ),
    )
    output_root = resolve_path(
        require_string(raw, "output_root", context),
        base_directory,
    )

    execution_raw = require_object(raw, "execution", context)
    reject_unknown_fields(
        execution_raw,
        {"workers", "max_in_flight", "overwrite", "on_frame_error"},
        "orchestrator.execution",
    )
    default_workers = min(os.cpu_count() or 1, 8)
    workers = optional_integer(
        execution_raw,
        "workers",
        default_workers,
        "orchestrator.execution",
        minimum=1,
    )
    max_in_flight = optional_integer(
        execution_raw,
        "max_in_flight",
        workers * 2,
        "orchestrator.execution",
        minimum=1,
    )
    if max_in_flight < workers:
        raise ValueError("orchestrator.execution.max_in_flight must be >= workers")
    on_frame_error = optional_string(
        execution_raw,
        "on_frame_error",
        "continue",
        "orchestrator.execution",
    )
    if on_frame_error not in {"continue", "fail_fast"}:
        raise ValueError(
            "orchestrator.execution.on_frame_error must be 'continue' or 'fail_fast'"
        )
    execution = ExecutionConfig(
        workers=workers,
        max_in_flight=max_in_flight,
        overwrite=optional_boolean(
            execution_raw,
            "overwrite",
            False,
            "orchestrator.execution",
        ),
        on_frame_error=on_frame_error,
    )

    output_raw = require_object(raw, "output", context)
    reject_unknown_fields(
        output_raw,
        {"image_mode", "write_manifest"},
        "orchestrator.output",
    )
    image_mode = optional_string(
        output_raw,
        "image_mode",
        "hardlink_or_copy",
        "orchestrator.output",
    )
    if image_mode not in {"hardlink_or_copy", "copy", "none"}:
        raise ValueError(
            "orchestrator.output.image_mode must be hardlink_or_copy, copy, or none"
        )
    output = OutputConfig(
        image_mode=image_mode,
        write_manifest=optional_boolean(
            output_raw,
            "write_manifest",
            True,
            "orchestrator.output",
        ),
    )

    raw_modules = require_list(raw, "modules", context)
    if not raw_modules:
        raise ValueError("orchestrator.modules must not be empty")
    modules = []
    used_ids = set()
    for index, item in enumerate(raw_modules):
        module_context = f"orchestrator.modules[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{module_context} must be a JSON object")
        reject_unknown_fields(
            item,
            {"id", "type", "enabled", "config", "depends_on"},
            module_context,
        )
        module_id = require_string(item, "id", module_context)
        if module_id in used_ids:
            raise ValueError(f"duplicate module id: {module_id}")
        used_ids.add(module_id)
        depends_raw = item.get("depends_on", [])
        if not isinstance(depends_raw, list) or not all(
            isinstance(value, str) and value.strip() for value in depends_raw
        ):
            raise ValueError(f"{module_context}.depends_on must be an array of strings")
        depends_on = tuple(value.strip() for value in depends_raw)
        if len(set(depends_on)) != len(depends_on):
            raise ValueError(f"{module_context}.depends_on contains duplicates")
        modules.append(
            ModuleSpec(
                module_id=module_id,
                module_type=require_string(item, "type", module_context),
                enabled=optional_boolean(item, "enabled", True, module_context),
                config_path=resolve_path(
                    require_string(item, "config", module_context),
                    base_directory,
                ),
                depends_on=depends_on,
            )
        )

    config = OrchestratorConfig(
        config_path=path,
        inputs=inputs,
        output_root=output_root,
        execution=execution,
        output=output,
        modules=tuple(modules),
    )

    if not inputs.rgb_dir.is_dir():
        raise FileNotFoundError(f"RGB directory does not exist: {inputs.rgb_dir}")
    if not inputs.semantic_dir.is_dir():
        raise FileNotFoundError(
            f"semantic directory does not exist: {inputs.semantic_dir}"
        )
    if not inputs.semantic_mapping.is_file():
        raise FileNotFoundError(
            f"semantic mapping does not exist: {inputs.semantic_mapping}"
        )

    all_by_id = {item.module_id: item for item in modules}
    enabled_ids = {item.module_id for item in modules if item.enabled}
    for item in config.enabled_modules:
        if not item.config_path.is_file():
            raise FileNotFoundError(
                f"config for module {item.module_id!r} does not exist: {item.config_path}"
            )
        for dependency in item.depends_on:
            if dependency not in all_by_id:
                raise ValueError(
                    f"module {item.module_id!r} depends on unknown module {dependency!r}"
                )
            if dependency not in enabled_ids:
                raise ValueError(
                    f"module {item.module_id!r} depends on disabled module {dependency!r}"
                )
            if dependency == item.module_id:
                raise ValueError(f"module {item.module_id!r} depends on itself")

    config.ordered_modules()
    _validate_input_output_separation(config)
    return config
