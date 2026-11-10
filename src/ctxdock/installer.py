"""Safe user-level Agent Skill installation."""

from __future__ import annotations

import shutil
from importlib import resources
from pathlib import Path


def default_target() -> Path:
    return Path.home() / ".agents" / "skills" / "ctxdock"


def source_skill() -> Path:
    return Path(str(resources.files("ctxdock").joinpath("_skill")))


def install(target: Path | None = None, upgrade: bool = False) -> Path:
    target = (target or default_target()).expanduser().resolve()
    if target.name.lower() != "ctxdock":
        raise ValueError("Skill target directory must be named 'ctxdock'.")
    if target.exists() and not upgrade:
        raise FileExistsError(f"A ctxdock skill already exists at {target}; use --upgrade to replace skill files.")
    if target.exists():
        skill_file = target / "SKILL.md"
        if not skill_file.is_file() or "name: ctxdock" not in skill_file.read_text(encoding="utf-8", errors="replace"):
            raise ValueError(f"Refusing to replace a directory that is not an identifiable ctxdock skill: {target}")
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_skill(), target)
    return target


def uninstall(target: Path | None = None) -> Path:
    target = (target or default_target()).expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError(f"CtxDock skill is not installed at {target}.")
    skill_file = target / "SKILL.md"
    if target.name.lower() != "ctxdock" or not skill_file.is_file() or "name: ctxdock" not in skill_file.read_text(encoding="utf-8", errors="replace"):
        raise ValueError(f"Refusing to remove a directory that is not an identifiable ctxdock skill: {target}")
    shutil.rmtree(target)
    return target
