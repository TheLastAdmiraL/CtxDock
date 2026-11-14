#!/usr/bin/env python3
"""Headless, non-interactive installer for CtxDock across coding agents.

Designed to be executed silently by AI agents (Antigravity, Claude Code,
Cursor, OpenAI Codex, Gemini CLI) after conducting an in-chat setup interview.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STANDALONE_SOURCE = ROOT / "skill" / "ctxdock"

CURSOR_RULE_CONTENT = """---
description: Project memory for architecture decisions, constraints, and handoffs
globs: *
alwaysApply: true
---

# CtxDock Memory

When starting complex tasks, retrieving context, or finalizing decisions, use CtxDock.
Run the local python runner:

```bash
python {script_path} find "<query>"
python {script_path} get <id> --summary
```

To record a finalized decision or constraint:
```bash
printf '%s' '{{"title":"...","summary":"...","category":"decision","tags":["..."]}}' | python {script_path} save
```

To view or record session handoffs:
```bash
python {script_path} handoff
```
"""

CLAUDE_MD_SNIPPET = """
## Project Memory (CtxDock)
Use CtxDock to search historical decisions, constraints, and session handoffs.
Run: `python {script_path} find "<query>"`
Save: `printf '%s' '{{"title":"...","summary":"...","category":"decision"}}' | python {script_path} save`
Handoff: `python {script_path} handoff`
"""


def find_git_root(path: Path) -> Path:
    current = path.resolve()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return parent
    return current


def install_skill_copy(target_dir: Path) -> Path:
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(STANDALONE_SOURCE, target_dir)
    return target_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Headless CtxDock multi-agent installer")
    parser.add_argument(
        "--mode",
        choices=["local", "global"],
        default="local",
        help="Installation scope: 'local' (inside this project) or 'global' (all projects on machine)",
    )
    parser.add_argument(
        "--agents",
        default="all",
        help="Comma-separated agent names (antigravity,cursor,claude,codex,gemini) or 'all'",
    )
    parser.add_argument(
        "--project-path",
        type=Path,
        default=None,
        help="Target project path for local mode (defaults to current working directory/git root)",
    )
    args = parser.parse_args()

    agent_list = [a.strip().lower() for a in args.agents.split(",") if a.strip()]
    install_all = "all" in agent_list

    installed_locations: list[str] = []

    if args.mode == "local":
        project_root = find_git_root(args.project_path or Path.cwd())
        ctxdock_dir = project_root / ".ctxdock"
        ctxdock_dir.mkdir(parents=True, exist_ok=True)

        # Create .gitignore inside .ctxdock to keep SQLite indices local and rebuildable
        gitignore_path = ctxdock_dir / ".gitignore"
        gitignore_path.write_text("*.db\n*.db-wal\n*.db-shm\nbackups/\n", encoding="utf-8")

        # Initialize local storage
        sys.path.insert(0, str(STANDALONE_SOURCE / "scripts"))
        try:
            import ctxdock as standalone_engine
            standalone_engine.Store(ctxdock_dir).init()
        except Exception:
            # Fallback direct directories
            (ctxdock_dir / "records").mkdir(parents=True, exist_ok=True)

        # Standalone skill location for this repository
        local_skill_dir = project_root / ".agent" / "skills" / "ctxdock"
        install_skill_copy(local_skill_dir)
        script_rel = ".agent/skills/ctxdock/scripts/ctxdock.py"
        installed_locations.append(f"Antigravity (.agent/skills/ctxdock): {local_skill_dir}")

        if install_all or "codex" in agent_list:
            codex_dir = project_root / ".agents" / "skills" / "ctxdock"
            if codex_dir != local_skill_dir:
                install_skill_copy(codex_dir)
            installed_locations.append(f"OpenAI Codex (.agents/skills/ctxdock): {codex_dir}")

        if install_all or "cursor" in agent_list:
            cursor_dir = project_root / ".cursor" / "rules"
            cursor_dir.mkdir(parents=True, exist_ok=True)
            cursor_file = cursor_dir / "ctxdock.mdc"
            cursor_file.write_text(CURSOR_RULE_CONTENT.format(script_path=script_rel), encoding="utf-8")
            installed_locations.append(f"Cursor (.cursor/rules/ctxdock.mdc): {cursor_file}")

        if install_all or "claude" in agent_list:
            claude_md = project_root / "CLAUDE.md"
            content = claude_md.read_text(encoding="utf-8") if claude_md.exists() else ""
            if "CtxDock" not in content:
                with claude_md.open("a", encoding="utf-8") as f:
                    f.write(CLAUDE_MD_SNIPPET.format(script_path=script_rel))
            installed_locations.append(f"Claude Code (CLAUDE.md): {claude_md}")

        if install_all or "gemini" in agent_list:
            gemini_dir = project_root / ".gemini" / "skills" / "ctxdock"
            install_skill_copy(gemini_dir)
            installed_locations.append(f"Gemini CLI (.gemini/skills/ctxdock): {gemini_dir}")

    else:
        # Global mode
        home = Path.home()
        global_ctxdock = home / ".ctxdock"
        global_ctxdock.mkdir(parents=True, exist_ok=True)

        # Initialize global storage
        sys.path.insert(0, str(STANDALONE_SOURCE / "scripts"))
        try:
            import ctxdock as standalone_engine
            standalone_engine.Store(global_ctxdock).init()
        except Exception:
            (global_ctxdock / "records").mkdir(parents=True, exist_ok=True)

        # Global skill installation
        global_skill_dir = home / ".agents" / "skills" / "ctxdock"
        install_skill_copy(global_skill_dir)
        global_script = str(global_skill_dir / "scripts" / "ctxdock.py")
        installed_locations.append(f"Global Agents (Antigravity & Codex) in ~/.agents/skills/ctxdock: {global_skill_dir}")

        if install_all or "cursor" in agent_list:
            cursor_home_dir = home / ".cursor" / "rules"
            cursor_home_dir.mkdir(parents=True, exist_ok=True)
            cursor_file = cursor_home_dir / "ctxdock.mdc"
            cursor_file.write_text(CURSOR_RULE_CONTENT.format(script_path=global_script), encoding="utf-8")
            installed_locations.append(f"Global Cursor (~/.cursor/rules/ctxdock.mdc): {cursor_file}")

        if install_all or "gemini" in agent_list:
            gemini_global = home / ".gemini" / "skills" / "ctxdock"
            install_skill_copy(gemini_global)
            installed_locations.append(f"Global Gemini (~/.gemini/skills/ctxdock): {gemini_global}")

    report = {
        "status": "success",
        "mode": args.mode,
        "storage": str(ctxdock_dir if args.mode == "local" else global_ctxdock),
        "installed": installed_locations,
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
