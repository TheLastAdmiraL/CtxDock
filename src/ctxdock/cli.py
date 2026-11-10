"""Command-line interface for CtxDock."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Sequence

from .installer import install as install_skill
from .installer import uninstall as uninstall_skill
from .security import SecurityError
from .storage import Store, bounded_json


def _json_input(inline: str | None, required: bool = True) -> dict[str, Any] | None:
    raw = inline if inline is not None else (sys.stdin.read() if not sys.stdin.isatty() else "")
    if not raw.strip():
        if required:
            raise ValueError("Provide a JSON object with --json or standard input.")
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON input: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("JSON input must be an object.")
    return value


def _common_project(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", help="Explicit stable project ID (defaults to detected repository)")


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ctxdock", description="Save what matters. Recall anywhere.")
    parser.add_argument("--home", type=Path, help="Override CTXDOCK_HOME for this command")
    parser.add_argument("--version", action="version", version="ctxdock 0.1.0")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Initialize global storage safely")

    save = sub.add_parser("save", help="Save a structured knowledge record from JSON")
    _common_project(save)
    save.add_argument("--json", help="Inline JSON object; stdin is recommended for multiline content")

    find = sub.add_parser("find", help="Search relevant knowledge with FTS5")
    _common_project(find)
    find.add_argument("query", nargs="+", help="Search terms")
    find.add_argument("--cross-project", action="store_true", help="Explicitly search every project")
    find.add_argument("--category")
    find.add_argument("--status", choices=["active", "superseded", "archived"])
    find.add_argument("--limit", type=_positive_int)
    find.add_argument("--detailed", action="store_true", help="Include full summaries and rationale")
    find.add_argument("--max-chars", type=_positive_int, help="Hard output character budget")

    get = sub.add_parser("get", help="Retrieve a record by stable ID")
    get.add_argument("record_id")
    get.add_argument("--summary", action="store_true", help="Return level-2 summary instead of full history")
    get.add_argument("--max-chars", type=_positive_int)

    listing = sub.add_parser("list", help="List knowledge for the current project")
    _common_project(listing)
    listing.add_argument("--cross-project", action="store_true")
    listing.add_argument("--category")
    listing.add_argument("--status", choices=["active", "superseded", "archived"])
    listing.add_argument("--since", help="ISO-8601 lower bound for updated_at")
    listing.add_argument("--limit", type=_positive_int, default=50)

    update = sub.add_parser("update", help="Update a record while preserving revision history")
    update.add_argument("record_id")
    update.add_argument("--json", help="JSON changes; may include expected_updated_at")

    handoff = sub.add_parser("handoff", help="Create a compact handoff, or retrieve the latest one")
    _common_project(handoff)
    handoff.add_argument("--json", help="Handoff fields as JSON; omit to retrieve latest")

    sub.add_parser("rebuild", help="Rebuild SQLite index from canonical JSON records")

    doctor = sub.add_parser("doctor", help="Check runtime, storage, FTS5, permissions, and skill")
    doctor.add_argument("--skill-dir", type=Path)

    stats = sub.add_parser("stats", help="Display local storage and retrieval statistics")
    _common_project(stats)

    install = sub.add_parser("install-skill", help="Install the Codex skill at user level")
    install.add_argument("--target", type=Path)
    install.add_argument("--upgrade", action="store_true")

    uninstall = sub.add_parser("uninstall-skill", help="Remove skill files but preserve all memories")
    uninstall.add_argument("--target", type=Path)
    return parser


def _compact_results(rows: list[dict[str, Any]], detailed: bool) -> list[dict[str, Any]]:
    keys = ("id", "title", "snippet", "category", "status", "relevance", "project_id", "scope")
    if detailed:
        keys += ("summary", "rationale", "tags", "source", "updated_at")
    return [{key: row.get(key) for key in keys if key in row} for row in rows]


def run(args: argparse.Namespace) -> int:
    store = Store(args.home)
    command = args.command
    if command == "init":
        result = store.init()
    elif command == "save":
        record, warnings = store.save(_json_input(args.json) or {}, args.project)
        result = {"record": record, "warnings": warnings}
    elif command == "find":
        rows = store.find(" ".join(args.query), args.project, cross_project=args.cross_project,
                          category=args.category, status=args.status, limit=args.limit)
        result = _compact_results(rows, args.detailed)
    elif command == "get":
        record = store.get(args.record_id)
        if args.summary:
            record = {key: record.get(key) for key in ("id", "title", "summary", "rationale", "category", "status", "source", "updated_at")}
        result = record
    elif command == "list":
        result = store.list_records(args.project, cross_project=args.cross_project, category=args.category,
                                    status=args.status, since=args.since, limit=args.limit)
    elif command == "update":
        changes = _json_input(args.json) or {}
        expected = changes.pop("expected_updated_at", None)
        record, warnings = store.update(args.record_id, changes, expected)
        result = {"record": record, "warnings": warnings}
    elif command == "handoff":
        result = store.handoff(_json_input(args.json, required=False), args.project)
    elif command == "rebuild":
        result = {"rebuilt_records": store.rebuild()}
    elif command == "doctor":
        result, ok = store.doctor(args.skill_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if ok else 1
    elif command == "stats":
        result = store.stats(args.project)
    elif command == "install-skill":
        result = {"installed": str(install_skill(args.target, args.upgrade)), "memories_preserved": True}
    elif command == "uninstall-skill":
        result = {"uninstalled": str(uninstall_skill(args.target)), "memories_preserved": True}
    else:
        raise AssertionError(f"Unhandled command: {command}")
    budget = getattr(args, "max_chars", None) or (store.config()["default_output_budget"] if command in {"find", "get"} else 100_000)
    print(bounded_json(result, int(budget)))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        return run(parser.parse_args(argv))
    except (ValueError, KeyError, FileNotFoundError, FileExistsError, PermissionError, RuntimeError, SecurityError, sqlite3.Error) as exc:
        print(f"ctxdock: error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("ctxdock: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
