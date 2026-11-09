"""Knowledge record construction and validation."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .security import SecurityError, inspect_text, safe_component

VALID_SCOPES = {"project", "shared"}
VALID_STATUSES = {"active", "superseded", "archived"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def content_hash(record: dict[str, Any]) -> str:
    payload = {
        key: record.get(key)
        for key in ("project_id", "scope", "category", "title", "summary", "rationale", "tags")
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def make_record(data: dict[str, Any], project_id: str) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(data, dict):
        raise ValueError("Record input must be a JSON object.")
    title = str(data.get("title", "")).strip()
    summary = str(data.get("summary", data.get("content", ""))).strip()
    if not title or not summary:
        raise ValueError("Both title and summary are required.")
    scope = str(data.get("scope", "project"))
    status = str(data.get("status", "active"))
    if scope not in VALID_SCOPES:
        raise ValueError(f"scope must be one of: {', '.join(sorted(VALID_SCOPES))}")
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(sorted(VALID_STATUSES))}")
    category = safe_component(str(data.get("category", "note")), "category")
    tags = data.get("tags", [])
    if isinstance(tags, str):
        tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise ValueError("tags must be a list of strings.")
    rationale = str(data.get("rationale", "")).strip()
    source = data.get("source") or {}
    if not isinstance(source, dict):
        raise ValueError("source must be an object.")
    warnings = inspect_text([title, summary, rationale, *tags, str(source.get("reference") or "")])
    now = utc_now()
    record: dict[str, Any] = {
        "id": f"mem-{uuid.uuid4().hex[:16]}",
        "project_id": project_id,
        "scope": scope,
        "category": category,
        "title": title,
        "summary": summary,
        "rationale": rationale,
        "tags": sorted(set(tags)),
        "status": status,
        "source": {
            "agent": source.get("agent"),
            "reference": source.get("reference"),
        },
        "created_at": now,
        "updated_at": now,
        "content_hash": "",
        "supersedes": data.get("supersedes"),
        "revisions": [],
    }
    record["content_hash"] = content_hash(record)
    return record, warnings


def validate_record_id(value: str) -> str:
    if not value.startswith("mem-"):
        raise SecurityError("Invalid record ID.")
    return safe_component(value, "record ID")

