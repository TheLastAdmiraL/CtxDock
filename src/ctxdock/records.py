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

# --- Payload size limits ---
MAX_TITLE_CHARS = 512
MAX_SUMMARY_CHARS = 65_536
MAX_RATIONALE_CHARS = 65_536
MAX_SOURCE_REFERENCE_CHARS = 4_096
MAX_TAGS = 64
MAX_TAG_CHARS = 128
MAX_INPUT_CHARS = 262_144


def _validate_field_limits(data: dict[str, Any]) -> None:
    """Reject records exceeding payload size limits before any writes."""
    raw_input = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if len(raw_input) > MAX_INPUT_CHARS:
        raise ValueError(f"Total input exceeds {MAX_INPUT_CHARS:,} characters ({len(raw_input):,} given).")
    title = str(data.get("title", ""))
    if len(title) > MAX_TITLE_CHARS:
        raise ValueError(f"title exceeds {MAX_TITLE_CHARS} characters ({len(title)} given).")
    summary = str(data.get("summary", data.get("content", "")))
    if len(summary) > MAX_SUMMARY_CHARS:
        raise ValueError(f"summary exceeds {MAX_SUMMARY_CHARS:,} characters ({len(summary):,} given).")
    rationale = str(data.get("rationale", ""))
    if len(rationale) > MAX_RATIONALE_CHARS:
        raise ValueError(f"rationale exceeds {MAX_RATIONALE_CHARS:,} characters ({len(rationale):,} given).")
    source = data.get("source") or {}
    if isinstance(source, dict):
        ref = str(source.get("reference") or "")
        if len(ref) > MAX_SOURCE_REFERENCE_CHARS:
            raise ValueError(f"source.reference exceeds {MAX_SOURCE_REFERENCE_CHARS:,} characters ({len(ref):,} given).")
    tags = data.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    if isinstance(tags, list):
        if len(tags) > MAX_TAGS:
            raise ValueError(f"tags exceeds {MAX_TAGS} entries ({len(tags)} given).")
        for tag in tags:
            if isinstance(tag, str) and len(tag) > MAX_TAG_CHARS:
                raise ValueError(f"A tag exceeds {MAX_TAG_CHARS} characters ({len(tag)} given).")


def check_legacy_limits(record: dict[str, Any]) -> list[str]:
    """Return warnings for oversized legacy records without rejecting them."""
    warnings: list[str] = []
    if len(str(record.get("title", ""))) > MAX_TITLE_CHARS:
        warnings.append(f"title exceeds {MAX_TITLE_CHARS} characters (legacy record)")
    if len(str(record.get("summary", ""))) > MAX_SUMMARY_CHARS:
        warnings.append(f"summary exceeds {MAX_SUMMARY_CHARS:,} characters (legacy record)")
    if len(str(record.get("rationale", ""))) > MAX_RATIONALE_CHARS:
        warnings.append(f"rationale exceeds {MAX_RATIONALE_CHARS:,} characters (legacy record)")
    tags = record.get("tags", [])
    if isinstance(tags, list) and len(tags) > MAX_TAGS:
        warnings.append(f"tags exceeds {MAX_TAGS} entries (legacy record)")
    return warnings


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
    _validate_field_limits(data)
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

