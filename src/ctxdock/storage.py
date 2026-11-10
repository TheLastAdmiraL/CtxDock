"""Canonical JSON storage coordinated with the SQLite search index."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
import shutil
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator

from . import __version__
from . import index
from .projects import resolve_project
from .records import VALID_STATUSES, check_legacy_limits, content_hash, make_record, utc_now, validate_record_id, _validate_field_limits
from .security import SecurityError, ensure_within, inspect_text, safe_component


DEFAULT_CONFIG = {
    "version": 1,
    "saving_policy": "suggest",
    "default_result_limit": 5,
    "default_output_budget": 2400,
}


def default_home() -> Path:
    override = os.environ.get("CTXDOCK_HOME")
    return Path(override).expanduser() if override else Path.home() / ".ctxdock"


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        delays = (0.02, 0.04, 0.08, 0.16, 0.32)
        for attempt, delay in enumerate(delays, start=1):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == len(delays):
                    raise PermissionError(
                        f"Could not atomically replace {path} after {attempt} attempts."
                    )
                time.sleep(delay)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except BaseException:
        try:
            Path(temporary).unlink(missing_ok=True)
        except OSError:
            pass
        raise


@contextmanager
def _file_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+b") as handle:
        fd = handle.fileno()
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                try:
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass


class Store:
    def __init__(self, home: Path | None = None):
        self.home = (home or default_home()).expanduser().resolve()
        self.db_path = self.home / "index.db"

    def init(self) -> dict[str, Any]:
        self.home.mkdir(parents=True, exist_ok=True)
        for name in ("records/global", "records/shared", "backups"):
            (self.home / name).mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.home, 0o700)
        except OSError:
            pass
        config_path = self.home / "config.json"
        if not config_path.exists():
            _atomic_json(config_path, DEFAULT_CONFIG)
        projects_path = self.home / "projects.json"
        if not projects_path.exists():
            _atomic_json(projects_path, {"version": 1, "projects": {}})
        index.initialize(self.db_path)
        return {"home": str(self.home), "database": str(self.db_path), "initialized": True}

    def require_init(self) -> None:
        if not self.db_path.exists():
            raise FileNotFoundError(f"CtxDock is not initialized at {self.home}. Run 'ctxdock init'.")

    def config(self) -> dict[str, Any]:
        self.require_init()
        try:
            value = json.loads((self.home / "config.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Invalid configuration: {exc}") from exc
        return {**DEFAULT_CONFIG, **value}

    def resolve_project(self, explicit_id: str | None = None, cwd: Path | None = None) -> dict[str, Any]:
        return resolve_project(self.home, explicit_id, cwd)

    def register_project(self, explicit_id: str | None = None, cwd: Path | None = None) -> dict[str, Any]:
        project = resolve_project(self.home, explicit_id, cwd)
        path = self.home / "projects.json"
        lock_path = self.home / ".projects.lock"
        with _file_lock(lock_path):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {"version": 1, "projects": {}}
            projects = data.setdefault("projects", {})
            if project["id"] not in projects or projects[project["id"]].get("root") != project["root"]:
                projects[project["id"]] = {
                    "name": project["name"],
                    "root": project["root"],
                    "created_at": projects.get(project["id"], {}).get("created_at") or utc_now(),
                }
                _atomic_json(path, data)
        return project

    def project(self, explicit_id: str | None = None, cwd: Path | None = None) -> dict[str, Any]:
        return self.resolve_project(explicit_id, cwd)

    def _record_path(self, record: dict[str, Any]) -> Path:
        bucket = "shared" if record["scope"] == "shared" else safe_component(record["project_id"], "project ID")
        path = self.home / "records" / bucket / f"{validate_record_id(record['id'])}.json"
        return ensure_within(self.home / "records", path)

    def save(self, data: dict[str, Any], project_id: str | None = None, cwd: Path | None = None) -> tuple[dict[str, Any], list[str]]:
        self.require_init()
        project = self.register_project(project_id or data.get("project_id"), cwd)
        record, warnings = make_record(data, project["id"])
        path = self._record_path(record)
        with index.connect(self.db_path) as conn:
            duplicate = conn.execute(
                "SELECT id FROM records WHERE project_id = ? AND scope = ? AND content_hash = ?",
                (record["project_id"], record["scope"], record["content_hash"]),
            ).fetchone()
            if duplicate:
                raise ValueError(f"Exact duplicate of existing record {duplicate['id']}.")
            _atomic_json(path, record)
            try:
                index.upsert(conn, record, path)
                if record.get("supersedes"):
                    old_id = validate_record_id(str(record["supersedes"]))
                    old = conn.execute("SELECT path FROM records WHERE id = ?", (old_id,)).fetchone()
                    if old:
                        old_record = json.loads(Path(old["path"]).read_text(encoding="utf-8"))
                        old_record["status"] = "superseded"
                        old_record["updated_at"] = utc_now()
                        _atomic_json(Path(old["path"]), old_record)
                        index.upsert(conn, old_record, Path(old["path"]))
            except Exception:
                path.unlink(missing_ok=True)
                raise
        return record, warnings

    def get(self, record_id: str) -> dict[str, Any]:
        self.require_init()
        record_id = validate_record_id(record_id)
        with index.connect(self.db_path) as conn:
            row = conn.execute("SELECT path FROM records WHERE id = ?", (record_id,)).fetchone()
        if not row:
            raise KeyError(f"Record not found: {record_id}")
        path = ensure_within(self.home / "records", Path(row["path"]))
        return json.loads(path.read_text(encoding="utf-8"))

    def find(
        self,
        query: str,
        project_id: str | None = None,
        cwd: Path | None = None,
        cross_project: bool = False,
        category: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        self.require_init()
        project = self.resolve_project(project_id, cwd)
        if status and status not in VALID_STATUSES:
            raise ValueError("Invalid status filter.")
        limit = limit or int(self.config()["default_result_limit"])
        with index.connect(self.db_path) as conn:
            return index.search(conn, query, project["id"], cross_project, category, status, limit)

    def list_records(
        self,
        project_id: str | None = None,
        cwd: Path | None = None,
        cross_project: bool = False,
        category: str | None = None,
        status: str | None = None,
        since: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self.require_init()
        project = self.resolve_project(project_id, cwd)
        clauses: list[str] = []
        params: list[Any] = []
        if not cross_project:
            clauses.append("(project_id = ? OR scope = 'shared')")
            params.append(project["id"])
        if category:
            clauses.append("category = ?")
            params.append(category)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if since:
            clauses.append("updated_at >= ?")
            params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(limit, 1000)))
        with index.connect(self.db_path) as conn:
            rows = conn.execute(
                f"SELECT * FROM records {where} ORDER BY updated_at DESC LIMIT ?", params
            ).fetchall()
        results = []
        for row in rows:
            rec = dict(row)
            rec["tags"] = json.loads(rec["tags"])
            if "source" in rec:
                try:
                    rec["source"] = json.loads(rec["source"]) if isinstance(rec["source"], str) else (rec["source"] or {})
                except (json.JSONDecodeError, TypeError):
                    rec["source"] = {}
            results.append(rec)
        return results

    def update(self, record_id: str, changes: dict[str, Any], expected_updated_at: str | None = None) -> tuple[dict[str, Any], list[str]]:
        current = self.get(record_id)
        if expected_updated_at and current["updated_at"] != expected_updated_at:
            raise RuntimeError("Record changed since it was read; update refused to prevent lost data.")
        allowed = {"title", "summary", "content", "rationale", "tags", "category", "status", "source", "scope"}
        unknown = set(changes) - allowed - {"expected_updated_at"}
        if unknown:
            raise ValueError(f"Fields cannot be updated: {', '.join(sorted(unknown))}")
        if "content" in changes and "summary" not in changes:
            changes["summary"] = changes.pop("content")
        updated = {**current, **{k: v for k, v in changes.items() if k in allowed}}
        _validate_field_limits(updated)
        if updated["status"] not in VALID_STATUSES:
            raise ValueError("Invalid status.")
        updated["category"] = safe_component(str(updated["category"]), "category")
        if updated["scope"] not in {"project", "shared"}:
            raise ValueError("Invalid scope.")
        if not str(updated.get("title", "")).strip() or not str(updated.get("summary", "")).strip():
            raise ValueError("Both title and summary are required.")
        tags = updated.get("tags", [])
        if isinstance(tags, str):
            tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError("tags must be a list of strings.")
        updated["tags"] = sorted(set(tags))
        source = updated.get("source") or {}
        if not isinstance(source, dict):
            raise ValueError("source must be an object.")
        warnings = inspect_text([updated["title"], updated["summary"], updated.get("rationale", ""), *tags, str(source.get("reference") or "")])
        revision = {k: v for k, v in current.items() if k != "revisions"}
        updated["revisions"] = [*current.get("revisions", []), revision]
        updated["updated_at"] = utc_now()
        updated["content_hash"] = content_hash(updated)
        old_path = self._record_path(current)
        new_path = self._record_path(updated)
        with index.connect(self.db_path) as conn:
            conflict = conn.execute(
                "SELECT id FROM records WHERE project_id=? AND scope=? AND content_hash=? AND id<>?",
                (updated["project_id"], updated["scope"], updated["content_hash"], updated["id"]),
            ).fetchone()
            if conflict:
                raise ValueError(f"Update would duplicate existing record {conflict['id']}.")
            _atomic_json(new_path, updated)
            index.upsert(conn, updated, new_path)
        if old_path != new_path:
            old_path.unlink(missing_ok=True)
        return updated, warnings

    def iter_record_files(self) -> Iterator[tuple[dict[str, Any], Path]]:
        records_root = self.home / "records"
        if not records_root.exists():
            return
        for path in sorted(records_root.glob("*/*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                validate_record_id(record["id"])
                yield record, path
            except (OSError, ValueError, KeyError, json.JSONDecodeError, SecurityError):
                continue

    def rebuild(self) -> int:
        self.home.mkdir(parents=True, exist_ok=True)
        try:
            index.initialize(self.db_path)
        except sqlite3.DatabaseError:
            backup = self.home / "backups" / f"index-corrupt-{int(time.time())}.db"
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(self.db_path, backup)
            index.initialize(self.db_path)
        return index.rebuild(self.db_path, self.iter_record_files())

    def handoff(self, data: dict[str, Any] | None, project_id: str | None = None, cwd: Path | None = None) -> dict[str, Any] | None:
        if data is None:
            rows = self.list_records(project_id, cwd, category="handoff", status="active", limit=1)
            return self.get(rows[0]["id"]) if rows else None
        fields = ("current_goal", "completed_work", "decisions", "important_files", "blockers", "next_actions")
        summary = "\n".join(f"{key.replace('_', ' ').title()}: {data[key]}" for key in fields if data.get(key))
        if not summary:
            raise ValueError("A handoff needs at least one handoff field.")
        latest = self.handoff(None, project_id, cwd)
        record, _warnings = self.save({
            "title": data.get("title", "Agent handoff"),
            "summary": summary,
            "rationale": data.get("rationale", "Compact continuity note for the next agent session."),
            "category": "handoff",
            "tags": data.get("tags", ["handoff"]),
            "source": data.get("source", {}),
            "supersedes": data.get("supersedes") or (latest["id"] if latest else None),
        }, project_id, cwd)
        return record

    def doctor(self, skill_dir: Path | None = None) -> tuple[dict[str, Any], bool]:
        import sys

        checks: dict[str, Any] = {
            "python": {"ok": sys.version_info >= (3, 11), "detail": sys.version.split()[0]},
            "home": {"ok": self.home.exists(), "detail": str(self.home)},
            "database": {"ok": False, "detail": str(self.db_path)},
            "fts5": {"ok": False, "detail": "not checked"},
            "records": {"ok": False, "detail": "not checked"},
            "permissions": {"ok": os.access(self.home, os.R_OK | os.W_OK) if self.home.exists() else False, "detail": "home must be readable and writable"},
        }
        try:
            self.require_init()
            with index.connect(self.db_path) as conn:
                conn.execute("SELECT count(*) FROM records").fetchone()
                conn.execute("SELECT count(*) FROM records_fts").fetchone()
            checks["database"]["ok"] = True
            checks["fts5"] = {"ok": True, "detail": "available"}
            record_count = 0
            legacy_warnings: list[str] = []
            for record, _path in self.iter_record_files():
                record_count += 1
                legacy_warnings.extend(check_legacy_limits(record))
            checks["records"] = {
                "ok": True,
                "detail": f"{record_count} readable JSON records" + (f" ({len(legacy_warnings)} legacy warnings)" if legacy_warnings else ""),
            }
            if legacy_warnings:
                checks["legacy_limits"] = {
                    "ok": True,
                    "warning": True,
                    "detail": legacy_warnings,
                }
        except Exception as exc:
            checks["database"]["detail"] = str(exc)
            checks["fts5"]["detail"] = str(exc)
        target = skill_dir or Path.home() / ".agents" / "skills" / "ctxdock"
        checks["skill"] = {"ok": (target / "SKILL.md").is_file(), "detail": str(target)}
        return checks, all(item["ok"] for item in checks.values())

    def stats(self, project_id: str | None = None, cwd: Path | None = None, cross_project: bool = False) -> dict[str, Any]:
        self.require_init()
        project = self.resolve_project(project_id, cwd)
        with index.connect(self.db_path) as conn:
            if cross_project:
                total = conn.execute("SELECT count(*) FROM records").fetchone()[0]
                groups = {row[0]: row[1] for row in conn.execute("SELECT project_id, count(*) FROM records GROUP BY project_id")}
                samples = [row[0] for row in conn.execute("SELECT title FROM records ORDER BY updated_at DESC LIMIT 10")]
            else:
                total = conn.execute(
                    "SELECT count(*) FROM records WHERE project_id = ? OR scope = 'shared'",
                    (project["id"],),
                ).fetchone()[0]
                groups = None
                samples = [
                    row[0]
                    for row in conn.execute(
                        "SELECT title FROM records WHERE project_id = ? OR scope = 'shared' ORDER BY updated_at DESC LIMIT 10",
                        (project["id"],),
                    )
                ]
        latencies: list[float] = []
        output_sizes: list[int] = []
        for sample in samples:
            start = time.perf_counter()
            try:
                output = json.dumps(self.find(sample, project["id"], cross_project=cross_project, limit=3))
            except ValueError:
                output = "[]"
            latencies.append((time.perf_counter() - start) * 1000)
            output_sizes.append(len(output.encode("utf-8")))
        storage_size = sum(path.stat().st_size for path in self.home.rglob("*") if path.is_file())
        avg_bytes = statistics.mean(output_sizes) if output_sizes else 0
        data: dict[str, Any] = {
            "total_records": total,
            "database_bytes": self.db_path.stat().st_size,
            "storage_bytes": storage_size,
            "sample_search_latency_ms": round(statistics.mean(latencies), 3) if latencies else None,
            "average_search_output_bytes": round(avg_bytes, 1),
            "estimated_retrieval_tokens": round(avg_bytes / 4) if output_sizes else 0,
            "token_estimate_note": "Character-based estimate (bytes / 4), not model-reported usage.",
            "ctxdock_version": __version__,
        }
        if cross_project:
            data["records_by_project"] = groups
        return data


def bounded_json(value: Any, max_chars: int) -> str:
    if max_chars < 2:
        raise ValueError("Output budget must be at least 2 characters.")
    text = json.dumps(value, ensure_ascii=False, indent=2)
    if len(text) <= max_chars:
        return text
    if max_chars < 24:
        return "{}"[:max_chars]
    preview_size = max_chars
    while preview_size >= 0:
        bounded = json.dumps({"truncated": True, "preview": text[:preview_size]}, ensure_ascii=False)
        if len(bounded) <= max_chars:
            return bounded
        preview_size -= max(1, len(bounded) - max_chars)
    return '{"truncated":true}'

