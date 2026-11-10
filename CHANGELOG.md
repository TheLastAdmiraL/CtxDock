# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project uses semantic versioning.

## [0.1.0] - 2026-11-10

### Added

- Local JSON and SQLite FTS5 knowledge storage with strict project isolation.
- `init`, `save`, `find`, `get`, `list`, `update`, `handoff`, `rebuild`, `doctor`, and `stats` CLI commands.
- Hard payload size limits (512-char title, 64 KB summary/rationale, 64 tags, 4 KB source ref, 256 KB input).
- Secret detection recognizing assignments while exempting explicit placeholders (`<redacted>`, `[removed]`, `${PASSWORD}`, `********`).
- Versioned SQLite database schema (version 2) with automated transaction-safe migration and backup.
- Single canonical skill source in `skill/ctxdock/` synchronized to packaged resource and validated with `--check`.
- Project-scoped statistics by default with `--cross-project` breakdown.
- Windows persistence hardening with exponential backoff on `PermissionError`.
- Safe Codex user-skill installer and concise `ctxdock` skill.
- Automated offline retrieval benchmarks with zero project isolation violations.

