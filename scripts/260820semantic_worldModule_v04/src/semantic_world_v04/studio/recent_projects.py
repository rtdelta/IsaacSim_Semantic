"""Small persistent recent-project list used by the standalone Studio."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from semantic_world_v04.output.io import atomic_write_json, read_json


class RecentProjectStore:
    def __init__(self, path: Path, *, limit: int = 8) -> None:
        self.path = Path(path)
        self.limit = max(1, int(limit))

    def list(self, *, existing_only: bool = False) -> List[Dict[str, Any]]:
        try:
            value = read_json(self.path)
        except (FileNotFoundError, OSError, TypeError, ValueError):
            return []
        raw = value.get("projects", []) if isinstance(value, dict) else []
        projects = []
        for item in raw:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                continue
            if existing_only and not Path(item["path"]).is_dir():
                continue
            projects.append(dict(item))
        return projects[: self.limit]

    def record(
        self,
        project_path: Path,
        *,
        project_id: str = "",
        name: str = "",
        usd_path: str = "",
        opened_at_utc: Optional[str] = None,
    ) -> None:
        normalized = str(Path(project_path).resolve())
        current = [item for item in self.list() if item.get("path") != normalized]
        entry = {
            "path": normalized,
            "project_id": str(project_id),
            "name": str(name),
            "usd_path": str(usd_path),
            "opened_at_utc": opened_at_utc
            or datetime.now(timezone.utc).isoformat(),
        }
        atomic_write_json(
            self.path,
            {"schema_version": 1, "projects": [entry, *current][: self.limit]},
        )
