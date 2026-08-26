from __future__ import annotations

from typing import Tuple

from ..config import ExecutionConfig
from .base import PixelCounterBackend
from .numpy_backend import NumpyBackend
from .torch_backend import TorchCudaBackend, torch_cuda_available
from .triton_backend import TritonCudaBackend, triton_cuda_available


def create_backend(
    execution: ExecutionConfig,
    target_ids: Tuple[int, ...],
) -> PixelCounterBackend:
    requested = execution.backend
    if requested == "auto":
        if triton_cuda_available(execution.device):
            requested = "triton_cuda"
        elif torch_cuda_available(execution.device):
            requested = "torch_cuda"
        else:
            requested = "numpy"

    if requested == "triton_cuda":
        return TritonCudaBackend(target_ids, execution.device)
    if requested == "torch_cuda":
        return TorchCudaBackend(target_ids, execution.device)
    if requested == "numpy":
        return NumpyBackend(target_ids, execution.cpu_workers)
    raise ValueError(f"unsupported backend: {requested}")

