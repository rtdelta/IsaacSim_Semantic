from __future__ import annotations

from typing import Dict, Type

from .module_base import PipelineModule, RunContext
from .orchestrator_config import ModuleSpec


_MODULE_TYPES: Dict[str, Type[PipelineModule]] = {}


def register_module(module_type: str):
    def decorator(cls: Type[PipelineModule]) -> Type[PipelineModule]:
        if not module_type:
            raise ValueError("module type must not be empty")
        previous = _MODULE_TYPES.get(module_type)
        if previous is not None and previous is not cls:
            raise ValueError(f"module type is already registered: {module_type}")
        cls.type_name = module_type
        _MODULE_TYPES[module_type] = cls
        return cls

    return decorator


def create_module(spec: ModuleSpec, run_context: RunContext) -> PipelineModule:
    try:
        module_class = _MODULE_TYPES[spec.module_type]
    except KeyError as exc:
        known = ", ".join(sorted(_MODULE_TYPES)) or "<none>"
        raise ValueError(
            f"unknown module type {spec.module_type!r}; registered types: {known}"
        ) from exc
    return module_class.from_config(spec, run_context)
