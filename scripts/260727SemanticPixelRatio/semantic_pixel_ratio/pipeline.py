from __future__ import annotations

import hashlib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Sequence, Tuple

import numpy as np

from .backends import create_backend
from .backends.numpy_backend import _count_frame
from .config import RunConfig
from .discovery import discover_frame_pairs, fingerprint_pairs
from .io.npy_reader import PrefetchingNpyReader
from .models import BatchCounts, FramePair, LoadedBatch
from .results.atomic_io import atomic_write_json
from .results.ledger import CountsLedger
from .results.lock import OutputLock
from .results.reporter import write_reports
from .semantic_io import (
    inspect_dataset_contract,
    load_semantic_mapping,
    mapping_sha256,
    resolve_target_ids,
)


PIPELINE_VERSION = "1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(
    config: RunConfig,
    pairs_fingerprint: str,
    mapping_digest: str,
    target_ids: Tuple[int, ...],
    shape: Tuple[int, int],
    dtype: str,
) -> str:
    structure = {
        "pipeline_version": PIPELINE_VERSION,
        "inputs": {
            "whole_scene_semantic_dir": str(
                config.inputs.whole_scene_semantic_dir
            ),
            "excavator_only_semantic_dir": str(
                config.inputs.excavator_only_semantic_dir
            ),
            "semantic_mapping": str(config.inputs.semantic_mapping),
            "pairs_fingerprint": pairs_fingerprint,
            "mapping_sha256": mapping_digest,
        },
        "targets": {
            "labels": list(config.targets.labels),
            "ids": list(target_ids),
            "group_name": config.targets.group_name,
        },
        "ratio": {
            "numerator": config.ratio.numerator,
            "denominator": config.ratio.denominator,
            "zero_denominator": config.ratio.zero_denominator,
            "over_one": config.ratio.over_one,
        },
        "dataset": {"shape": list(shape), "dtype": dtype},
    }
    encoded = json.dumps(
        structure,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _prepare_output(config: RunConfig) -> None:
    output_root = config.output.root
    if output_root.exists() and config.output.overwrite:
        lock_path = output_root / ".run.lock"
        if lock_path.exists():
            raise RuntimeError(f"cannot overwrite locked output: {lock_path}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    if (
        not config.output.resume
        and not config.output.overwrite
        and any(output_root.iterdir())
    ):
        raise FileExistsError(
            f"output root is not empty and resume is disabled: {output_root}"
        )


def _verify_batch(
    batch: LoadedBatch,
    result: BatchCounts,
    target_ids: Tuple[int, ...],
    remaining: int,
) -> int:
    if remaining <= 0:
        return 0
    target_array = np.asarray(target_ids, dtype=np.int64)
    verify_count = min(remaining, len(batch.pairs))
    for index in range(verify_count):
        expected = _count_frame(batch.data[index], target_array)
        actual = np.asarray(result.counts[index], dtype=np.uint32)
        if not np.array_equal(expected, actual):
            pair = batch.pairs[index]
            raise ValueError(
                f"backend verification failed for frame {pair.frame_id}: "
                f"expected={expected.tolist()}, actual={actual.tolist()}"
            )
    return verify_count


def _validate_batch_counts(
    result: BatchCounts,
    pixels_per_frame: int,
) -> None:
    if np.any(result.counts < 0):
        raise ValueError("backend returned a negative pixel count")
    if np.any(result.counts > pixels_per_frame):
        raise ValueError("backend returned a count larger than the frame")
    group_counts = result.counts.sum(axis=2, dtype=np.uint64)
    if np.any(group_counts > pixels_per_frame):
        raise ValueError(
            "sum of target counts exceeds the number of frame pixels"
        )


def _initial_manifest(
    config: RunConfig,
    config_fingerprint: str,
    pairs: Sequence[FramePair],
    target_ids: Tuple[int, ...],
    backend_name: str,
    shape: Tuple[int, int],
    dtype: str,
) -> Dict[str, object]:
    return {
        "schema_version": 1,
        "status": "running",
        "started_at": _utc_now(),
        "config_path": str(config.config_path),
        "config_fingerprint": config_fingerprint,
        "backend_requested": config.execution.backend,
        "backend_selected": backend_name,
        "inputs": {
            "whole_scene_semantic_dir": str(
                config.inputs.whole_scene_semantic_dir
            ),
            "excavator_only_semantic_dir": str(
                config.inputs.excavator_only_semantic_dir
            ),
            "semantic_mapping": str(config.inputs.semantic_mapping),
        },
        "dataset": {
            "frames": len(pairs),
            "shape": list(shape),
            "dtype": dtype,
        },
        "targets": [
            {"label": label, "semantic_id": semantic_id}
            for label, semantic_id in zip(config.targets.labels, target_ids)
        ],
        "group_name": config.targets.group_name,
        "execution": {
            "batch_frames": config.execution.batch_frames,
            "reader_threads": config.execution.reader_threads,
            "ring_slots": config.execution.ring_slots,
            "cpu_workers": config.execution.cpu_workers,
            "device": config.execution.device,
            "verify_sample_frames": config.execution.verify_sample_frames,
        },
    }


def run(config: RunConfig) -> Dict[str, object]:
    started = time.perf_counter()
    mapping = load_semantic_mapping(config.inputs.semantic_mapping)
    target_ids = resolve_target_ids(mapping, config.targets.labels)
    pairs = discover_frame_pairs(
        config.inputs.whole_scene_semantic_dir,
        config.inputs.excavator_only_semantic_dir,
    )
    contract = inspect_dataset_contract(pairs[0], mapping.expected_dtype)
    pairs_digest = fingerprint_pairs(pairs)
    mapping_digest = mapping_sha256(config.inputs.semantic_mapping)
    config_fingerprint = _fingerprint(
        config,
        pairs_digest,
        mapping_digest,
        target_ids,
        contract.shape,
        str(contract.dtype),
    )

    _prepare_output(config)
    with OutputLock(config.output.root):
        with create_backend(config.execution, target_ids) as backend:
            manifest = _initial_manifest(
                config,
                config_fingerprint,
                pairs,
                target_ids,
                backend.name,
                contract.shape,
                str(contract.dtype),
            )
            ledger = CountsLedger(
                output_root=config.output.root,
                config_fingerprint=config_fingerprint,
                expected_frames=len(pairs),
                target_labels=config.targets.labels,
                backend_name=backend.name,
                resume=config.output.resume,
            )
            atomic_write_json(config.output.root / "manifest.json", manifest)
            remaining_pairs = pairs[ledger.completed_frames :]
            verified = 0
            try:
                reader = PrefetchingNpyReader(
                    pairs=remaining_pairs,
                    contract=contract,
                    batch_frames=config.execution.batch_frames,
                    reader_threads=config.execution.reader_threads,
                    ring_slots=config.execution.ring_slots,
                )
                for loaded_batch in reader:
                    result = backend.count_batch(loaded_batch)
                    _validate_batch_counts(result, contract.pixels_per_frame)
                    if backend.name != "numpy":
                        verified += _verify_batch(
                            loaded_batch,
                            result,
                            target_ids,
                            config.execution.verify_sample_frames - verified,
                        )
                    ledger.append(result)
                    completed = ledger.completed_frames
                    if completed % 1000 == 0 or completed == len(pairs):
                        print(
                            f"completed {completed}/{len(pairs)} frames "
                            f"with {backend.name}"
                        )

                ledger.mark_completed()
                ledger_data = ledger.load_all()
                elapsed = time.perf_counter() - started
                summary = write_reports(
                    output_root=config.output.root,
                    ledger=ledger_data,
                    targets=config.targets,
                    ratio_config=config.ratio,
                    pixels_per_frame=contract.pixels_per_frame,
                    backend_name=backend.name,
                    elapsed_seconds=elapsed,
                    write_cache=config.output.write_counts_cache,
                )
                manifest["status"] = "completed"
                manifest["finished_at"] = _utc_now()
                manifest["verified_sample_frames"] = verified
                manifest["summary"] = summary
                atomic_write_json(
                    config.output.root / "manifest.json",
                    manifest,
                )
                return summary
            except BaseException as exc:
                ledger.mark_failed(f"{type(exc).__name__}: {exc}")
                manifest["status"] = "failed"
                manifest["finished_at"] = _utc_now()
                manifest["error"] = f"{type(exc).__name__}: {exc}"
                atomic_write_json(
                    config.output.root / "manifest.json",
                    manifest,
                )
                raise
