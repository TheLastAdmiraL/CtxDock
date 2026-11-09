"""SQLite metadata and FTS5 search index."""

from __future__ import annotations

import json
from difflib import SequenceMatcher
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
CREATE TABLE IF NOT EXISTS records (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  rationale TEXT NOT NULL,
  tags TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_records_project ON records(project_id, scope, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_records_hash ON records(project_id, scope, content_hash);
CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
  id UNINDEXED, title, summary, rationale, tags, tokenize='unicode61'
);
"""


class ClosingConnection(sqlite3.Connection):
    """A sqlite connection whose context manager also releases file handles."""

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc, traceback))
        finally:
            self.close()


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def initialize(path: Path) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)


def upsert(conn: sqlite3.Connection, record: dict[str, Any], path: Path) -> None:
    values = (
        record["id"], record["project_id"], record["scope"], record["category"], record["title"],
        record["summary"], record.get("rationale", ""), json.dumps(record.get("tags", [])),
        record["status"], record["created_at"], record["updated_at"], record["content_hash"], str(path),
    )
    conn.execute("DELETE FROM records_fts WHERE id = ?", (record["id"],))
    conn.execute("DELETE FROM records WHERE id = ?", (record["id"],))
    conn.execute(
        "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values
    )
    conn.execute(
        "INSERT INTO records_fts(id, title, summary, rationale, tags) VALUES (?, ?, ?, ?, ?)",
        (record["id"], record["title"], record["summary"], record.get("rationale", ""), " ".join(record.get("tags", []))),
    )


def fts_query(text: str) -> str:
    terms = re.findall(r"[\w]+", text, flags=re.UNICODE)
    return " AND ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms[:20])


def search(
    conn: sqlite3.Connection,
    query: str,
    project_id: str,
    cross_project: bool = False,
    category: str | None = None,
    status: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    match = fts_query(query)
    if not match:
        raise ValueError("Search query must contain at least one word or number.")
    where = ["records_fts MATCH ?"]
    params: list[Any] = [match]
    if not cross_project:
        where.append("(r.project_id = ? OR r.scope = 'shared')")
        params.append(project_id)
    if category:
        where.append("r.category = ?")
        params.append(category)
    if status:
        where.append("r.status = ?")
        params.append(status)
    sql = f"""
      SELECT r.*, bm25(records_fts, 0.0, 8.0, 3.0, 1.5, 1.0) AS raw_rank,
             snippet(records_fts, 2, '', '', ' … ', 18) AS snippet
      FROM records_fts JOIN records r ON r.id = records_fts.id
      WHERE {' AND '.join(where)}
      ORDER BY CASE r.status WHEN 'active' THEN 0 WHEN 'superseded' THEN 1 ELSE 2 END,
               raw_rank ASC, r.updated_at DESC
      LIMIT ?
    """
    params.append(max(1, min(limit, 100)))
    rows = conn.execute(sql, params).fetchall()
    if not rows and " AND " in match:
        fallback_params = list(params)
        fallback_params[0] = match.replace(" AND ", " OR ")
        rows = conn.execute(sql, fallback_params).fetchall()
    results = []
    seen_hashes: set[str] = set()
    seen_texts: list[str] = []
    for row in rows:
        item = dict(row)
        if item["content_hash"] in seen_hashes:
            continue
        normalized = re.sub(r"\W+", " ", f"{item['title']} {item['summary']}".lower()).strip()
        if any(SequenceMatcher(None, normalized, previous).ratio() >= 0.94 for previous in seen_texts):
            continue
        seen_hashes.add(item["content_hash"])
        seen_texts.append(normalized)
        item["relevance"] = round(1.0 / (1.0 + abs(float(item.pop("raw_rank")))), 4)
        item["tags"] = json.loads(item["tags"])
        results.append(item)
    return results


def rebuild(db_path: Path, records: Iterable[tuple[dict[str, Any], Path]]) -> int:
    with connect(db_path) as conn:
        conn.execute("DELETE FROM records_fts")
        conn.execute("DELETE FROM records")
        count = 0
        for record, path in records:
            upsert(conn, record, path)
            count += 1
    return count
