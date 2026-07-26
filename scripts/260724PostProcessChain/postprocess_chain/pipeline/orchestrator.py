from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence

from ..common.error_report import ErrorJournal
from ..common.frame_discovery import discover_frame_tasks
from ..common.output_writer import atomic_write_json
from ..common.semantic_io import load_semantic_mapping
from .executor import execute_frame_tasks
from .module_base import PipelineModule, RunContext
from .module_registry import create_module
from .orchestrator_config import OrchestratorConfig


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _config_fingerprint(config: OrchestratorConfig) -> str:
    digest = hashlib.sha256()
    structure = {
        "inputs": {
            "rgb_dir": str(config.inputs.rgb_dir),
            "semantic_dir": str(config.inputs.semantic_dir),
        },
        "modules": [
            {
                "id": item.module_id,
                "type": item.module_type,
                "depends_on": list(item.depends_on),
            }
            for item in config.ordered_modules()
        ],
    }
    digest.update(
        json.dumps(structure, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    digest.update(b"\0")
    files = [
        config.inputs.semantic_mapping,
        *(item.config_path for item in config.enabled_modules),
    ]
    for path in files:
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _initial_module_stats(modules: Sequence[PipelineModule]) -> Dict[str, Dict[str, int]]:
    return {
        module.module_id: {
            "written": 0,
            "skipped": 0,
            "excluded": 0,
            "success": 0,
            "error": 0,
            "blocked": 0,
            "boxes": 0,
        }
        for module in modules
    }


class Orchestrator:
    def __init__(self, config: OrchestratorConfig) -> None:
        self.config = config

    def _create_modules(self, run_context: RunContext) -> List[PipelineModule]:
        # Importing built-ins performs explicit registry registration.
        from .. import modules as _built_in_modules  # noqa: F401

        modules = [
            create_module(spec, run_context)
            for spec in self.config.ordered_modules()
        ]
        output_dirs = {}
        for module in modules:
            module.validate(run_context)
            previous = output_dirs.get(module.output_dir)
            if previous is not None:
                raise ValueError(
                    f"modules {previous!r} and {module.module_id!r} share output "
                    f"directory {module.output_dir}"
                )
            output_dirs[module.output_dir] = module.module_id
        return modules

    def _prepare_manifest(self, fingerprint: str, module_ids: Sequence[str]) -> Dict[str, object]:
        manifest_path = self.config.output_root / "manifest.json"
        if manifest_path.exists() and not self.config.execution.overwrite:
            try:
                previous = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"existing manifest is unreadable: {manifest_path}"
                ) from exc
            if previous.get("config_fingerprint") != fingerprint:
                raise ValueError(
                    "output_root contains results from a different configuration; "
                    "use a new output_root or set execution.overwrite=true"
                )

        return {
            "schema_version": 1,
            "status": "running",
            "started_at": _utc_now(),
            "config_path": str(self.config.config_path),
            "config_fingerprint": fingerprint,
            "inputs": {
                "rgb_dir": str(self.config.inputs.rgb_dir),
                "semantic_dir": str(self.config.inputs.semantic_dir),
                "semantic_mapping": str(self.config.inputs.semantic_mapping),
            },
            "modules": list(module_ids),
        }

    def run(self) -> int:
        semantic_mapping = load_semantic_mapping(
            self.config.inputs.semantic_mapping
        )
        tasks = discover_frame_tasks(
            self.config.inputs.rgb_dir,
            self.config.inputs.semantic_dir,
        )
        self.config.output_root.mkdir(parents=True, exist_ok=True)

        run_context = RunContext(
            output_root=self.config.output_root,
            label_to_id=semantic_mapping.label_to_id,
            expected_dtype=semantic_mapping.expected_dtype,
            overwrite=self.config.execution.overwrite,
            image_mode=self.config.output.image_mode,
        )
        modules = self._create_modules(run_context)

        fingerprint = _config_fingerprint(self.config)
        manifest = self._prepare_manifest(
            fingerprint,
            [module.module_id for module in modules],
        )
        for module in modules:
            module.prepare(run_context)
        if self.config.output.write_manifest:
            atomic_write_json(self.config.output_root / "manifest.json", manifest)

        module_stats = _initial_module_stats(modules)
        frames_completed = 0
        frames_failed = 0
        started = time.perf_counter()

        with ErrorJournal(self.config.output_root) as journal:
            for result in execute_frame_tasks(
                tasks=tasks,
                modules=modules,
                expected_dtype=semantic_mapping.expected_dtype,
                execution=self.config.execution,
                image_mode=self.config.output.image_mode,
            ):
                frames_completed += 1
                if result["status"] == "error":
                    frames_failed += 1
                for error in result["errors"]:
                    journal.write(error)

                for module_id, module_result in result["modules"].items():
                    stats = module_stats[module_id]
                    status = str(module_result["status"])
                    if status not in stats:
                        stats[status] = 0
                    stats[status] += 1
                    stats["boxes"] += int(module_result.get("boxes", 0))
                    for name, value in module_result.get("metrics", {}).items():
                        stats[name] = stats.get(name, 0) + int(value)

                if frames_completed % 100 == 0:
                    print(
                        f"completed {frames_completed}/{len(tasks)} frames, "
                        f"failed={frames_failed}"
                    )

        for module in modules:
            module.finalize()

        elapsed = time.perf_counter() - started
        summary = {
            "schema_version": 1,
            "discovered_frames": len(tasks),
            "completed_frames": frames_completed,
            "failed_frames": frames_failed,
            "stopped_early": frames_completed < len(tasks),
            "elapsed_seconds": round(elapsed, 6),
            "frames_per_second": round(frames_completed / elapsed, 6)
            if elapsed
            else 0.0,
            "modules": module_stats,
        }
        atomic_write_json(self.config.output_root / "summary.json", summary)

        if self.config.output.write_manifest:
            manifest["status"] = "failed" if frames_failed else "completed"
            manifest["finished_at"] = _utc_now()
            manifest["summary"] = summary
            atomic_write_json(self.config.output_root / "manifest.json", manifest)

        print("post-process chain completed")
        print(f"discovered frames: {len(tasks)}")
        print(f"completed frames: {frames_completed}")
        print(f"failed frames: {frames_failed}")
        for module_id, stats in module_stats.items():
            print(
                f"{module_id}: written={stats['written']}, "
                f"skipped={stats['skipped']}, excluded={stats['excluded']}, "
                f"errors={stats['error']}, boxes={stats['boxes']}"
            )
        return 1 if frames_failed else 0
