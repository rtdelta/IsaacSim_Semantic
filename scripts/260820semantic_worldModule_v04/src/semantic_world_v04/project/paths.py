"""Portable project path rules."""

import os
import re
from pathlib import Path
from typing import Optional

_URI_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")


class ProjectPathResolver:
    """Resolve local file references without rewriting USD/Nucleus URLs."""

    @staticmethod
    def is_uri(value: str) -> bool:
        return bool(_URI_RE.match(value))

    @staticmethod
    def is_absolute(value: str) -> bool:
        return (
            os.path.isabs(value)
            or bool(_WINDOWS_ABSOLUTE_RE.match(value))
            or value.startswith("/")
        )

    @classmethod
    def resolve(cls, value: Optional[str], project_dir: Path) -> Optional[str]:
        if value is None or cls.is_uri(value) or cls.is_absolute(value):
            return value
        return str((project_dir / value).resolve())

    @classmethod
    def make_relative(cls, value: str, project_dir: Path) -> str:
        if cls.is_uri(value):
            return value
        candidate = Path(value)
        try:
            return str(candidate.resolve().relative_to(project_dir.resolve()))
        except (OSError, ValueError):
            return value

