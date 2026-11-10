"""Input validation and secret detection."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable


class SecurityError(ValueError):
    """Raised when content is unsafe to persist."""


_SECRET_PATTERNS = [
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{30,})\b")),
    ("OpenAI-style API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("password assignment", re.compile(
        r"""(?ix)
        (?:
            \b(?:password|passwd|pwd|db_password|admin_pwd)\b\s*[:=]\s*
            |
            "(?:password|passwd|pwd|db_password|admin_pwd)"\s*:\s*
        )
        (?:
            (['"])
            (?!<redacted>|\[removed\]|\$\{[A-Za-z0-9_]+\}|\*{4,})
            [^\r\n"']{8,}
            \1
            |
            (?!<redacted>|\[removed\]|\$\{[A-Za-z0-9_]+\}|\*{4,})
            [^\s'",;]{8,}
        )
        """
    )),
]

_SENSITIVE_PATTERNS = [
    ("email address", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("private network address", re.compile(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})\b")),
]


def inspect_text(texts: Iterable[str]) -> list[str]:
    combined = "\n".join(str(value) for value in texts if value)
    for label, pattern in _SECRET_PATTERNS:
        if pattern.search(combined):
            raise SecurityError(f"Refusing to store content that appears to contain a {label}.")
    return [label for label, pattern in _SENSITIVE_PATTERNS if pattern.search(combined)]


def safe_component(value: str, label: str = "path component") -> str:
    if not value or value in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
        raise SecurityError(f"Invalid {label}: use letters, numbers, dots, underscores, or hyphens.")
    return value


def _normalize_path(p: Path) -> str:
    """Resolve and normalize a path for safe comparison.

    Strips extended-length path prefixes (``\\\\?\\`` and ``\\\\?\\UNC\\``) that
    Windows can produce, then applies ``os.path.normcase`` so drive-letter
    casing and separator differences are handled consistently.
    """
    resolved = str(p.resolve())
    # \\?\UNC\server\share  → \\server\share
    if resolved.startswith("\\\\?\\UNC\\"):
        resolved = "\\\\" + resolved[8:]
    # \\?\C:\…  → C:\…
    elif resolved.startswith("\\\\?\\"):
        resolved = resolved[4:]
    return os.path.normcase(resolved)


def ensure_within(base: Path, candidate: Path) -> Path:
    base_norm = _normalize_path(base)
    candidate_norm = _normalize_path(candidate)
    try:
        common = os.path.commonpath([base_norm, candidate_norm])
    except ValueError:
        # Different drives / mount points on Windows
        raise SecurityError(f"Unsafe path outside CtxDock storage: {candidate}")
    if os.path.normcase(common) != os.path.normcase(base_norm):
        raise SecurityError(f"Unsafe path outside CtxDock storage: {candidate}")
    return candidate.resolve()

