"""Stable project identification without storing data in repositories."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .security import safe_component


def git_root(cwd: Path | None = None) -> Path | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return Path(proc.stdout.strip()).resolve()


def derived_project_id(root: Path) -> str:
    normalized = os.path.normcase(str(root.resolve())).replace("\\", "/")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    stem = "".join(ch.lower() if ch.isalnum() else "-" for ch in root.name).strip("-") or "project"
    return f"{stem[:40]}-{digest}"


def resolve_project(home: Path, explicit_id: str | None = None, cwd: Path | None = None) -> dict[str, Any]:
    root = git_root(cwd) or (cwd or Path.cwd()).resolve()
    project_id = safe_component(explicit_id, "project ID") if explicit_id else derived_project_id(root)
    path = home / "projects.json"
    data: dict[str, Any] = {"version": 1, "projects": {}}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    entry = data.setdefault("projects", {}).get(project_id, {})
    return {
        "id": project_id,
        "name": entry.get("name") or root.name,
        "root": entry.get("root") or str(root),
    }

