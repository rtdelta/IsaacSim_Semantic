from __future__ import annotations

from typing import Tuple

import numpy as np

from ..models import BatchCounts, LoadedBatch
from .base import PixelCounterBackend


def torch_cuda_available(device: str = "cuda") -> bool:
    try:
        import torch
    except ImportError:
        return False
    return device.startswith("cuda") and torch.cuda.is_available()


class TorchCudaBackend(PixelCounterBackend):
    name = "torch_cuda"

    def __init__(self, target_ids: Tuple[int, ...], device: str) -> None:
        super().__init__(target_ids)
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("torch_cuda backend requires PyTorch") from exc
        if not torch_cuda_available(device):
            raise RuntimeError(f"CUDA device is unavailable: {device}")
        self._torch = torch
        self._device = torch.device(device)
        self._target_ids = torch.tensor(
            target_ids,
            dtype=torch.int32,
            device=self._device,
        )

    def count_batch(self, batch: LoadedBatch) -> BatchCounts:
        torch = self._torch
        host = torch.from_numpy(batch.data)
        if not host.is_pinned():
            host = host.pin_memory()
        device_data = host.to(self._device, non_blocking=True)
        target_ids = self._target_ids
        per_target = [
            torch.count_nonzero(device_data == target_ids[index], dim=(-2, -1))
            for index in range(5)
        ]
        counts = torch.stack(per_target, dim=-1)
        cpu_counts = counts.to(device="cpu", dtype=torch.int64).numpy()
        return BatchCounts(
            pairs=batch.pairs,
            counts=np.asarray(cpu_counts, dtype=np.uint32),
        )

