from __future__ import annotations

from typing import Tuple

import numpy as np

from ..models import BatchCounts, LoadedBatch
from .base import PixelCounterBackend
from .torch_backend import torch_cuda_available


try:
    import torch
    import triton
    import triton.language as tl
except ImportError:  # pragma: no cover - exercised on non-GPU environments
    torch = None
    triton = None
    tl = None


if triton is not None:

    @triton.jit
    def _count_partials_kernel(
        data_ptr,
        target_ptr,
        partial_ptr,
        pixels_per_frame,
        tiles_per_frame: tl.constexpr,
        block_pixels: tl.constexpr,
        target_count: tl.constexpr,
    ):
        frame_index = tl.program_id(0)
        tile_index = tl.program_id(1)
        offsets = tile_index * block_pixels + tl.arange(0, block_pixels)
        mask = offsets < pixels_per_frame
        source_stride = pixels_per_frame
        frame_stride = 2 * pixels_per_frame

        whole = tl.load(
            data_ptr + frame_index * frame_stride + offsets,
            mask=mask,
            other=0,
        ).to(tl.int32)
        reference = tl.load(
            data_ptr
            + frame_index * frame_stride
            + source_stride
            + offsets,
            mask=mask,
            other=0,
        ).to(tl.int32)

        partial_base = (
            (frame_index * tiles_per_frame + tile_index)
            * 2
            * target_count
        )
        for target_index in tl.static_range(0, target_count):
            semantic_id = tl.load(target_ptr + target_index).to(tl.int32)
            whole_count = tl.sum((whole == semantic_id) & mask, axis=0)
            reference_count = tl.sum(
                (reference == semantic_id) & mask,
                axis=0,
            )
            tl.store(
                partial_ptr + partial_base + target_index,
                whole_count,
            )
            tl.store(
                partial_ptr
                + partial_base
                + target_count
                + target_index,
                reference_count,
            )

    @triton.jit
    def _reduce_partials_kernel(
        partial_ptr,
        output_ptr,
        tiles_per_frame: tl.constexpr,
        reduce_block: tl.constexpr,
        target_count: tl.constexpr,
    ):
        output_index = tl.program_id(0)
        frame_index = output_index // (2 * target_count)
        remainder = output_index % (2 * target_count)
        source_index = remainder // target_count
        target_index = remainder % target_count
        tile_offsets = tl.arange(0, reduce_block)
        mask = tile_offsets < tiles_per_frame
        offsets = (
            ((frame_index * tiles_per_frame + tile_offsets) * 2 + source_index)
            * target_count
            + target_index
        )
        values = tl.load(partial_ptr + offsets, mask=mask, other=0)
        total = tl.sum(values, axis=0)
        tl.store(output_ptr + output_index, total)


def triton_cuda_available(device: str = "cuda") -> bool:
    return (
        triton is not None
        and torch is not None
        and torch_cuda_available(device)
    )


def _next_power_of_two(value: int) -> int:
    return 1 if value <= 1 else 1 << (value - 1).bit_length()


class TritonCudaBackend(PixelCounterBackend):
    name = "triton_cuda"

    def __init__(
        self,
        target_ids: Tuple[int, ...],
        device: str,
        block_pixels: int = 16384,
    ) -> None:
        super().__init__(target_ids)
        if not triton_cuda_available(device):
            raise RuntimeError(
                "triton_cuda backend requires CUDA-enabled PyTorch and Triton"
            )
        if block_pixels <= 0 or block_pixels & (block_pixels - 1):
            raise ValueError("Triton block_pixels must be a positive power of two")
        self._device = torch.device(device)
        self._target_ids = torch.tensor(
            target_ids,
            dtype=torch.int32,
            device=self._device,
        )
        self._block_pixels = block_pixels

    def count_batch(self, batch: LoadedBatch) -> BatchCounts:
        host = torch.from_numpy(batch.data)
        if not host.is_pinned():
            host = host.pin_memory()
        device_data = host.to(self._device, non_blocking=True)
        frames = len(batch.pairs)
        pixels = int(batch.data.shape[2] * batch.data.shape[3])
        tiles = triton.cdiv(pixels, self._block_pixels)
        partial = torch.empty(
            (frames, tiles, 2, 5),
            dtype=torch.int32,
            device=self._device,
        )
        output = torch.empty(
            (frames, 2, 5),
            dtype=torch.int32,
            device=self._device,
        )

        _count_partials_kernel[(frames, tiles)](
            device_data,
            self._target_ids,
            partial,
            pixels,
            tiles_per_frame=tiles,
            block_pixels=self._block_pixels,
            target_count=5,
            num_warps=8,
        )
        reduce_block = _next_power_of_two(tiles)
        _reduce_partials_kernel[(frames * 2 * 5,)](
            partial,
            output,
            tiles_per_frame=tiles,
            reduce_block=reduce_block,
            target_count=5,
            num_warps=1,
        )
        cpu_counts = output.to(device="cpu", dtype=torch.int64).numpy()
        return BatchCounts(
            pairs=batch.pairs,
            counts=np.asarray(cpu_counts, dtype=np.uint32),
        )
