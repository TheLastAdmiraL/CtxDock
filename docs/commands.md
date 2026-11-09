# Command reference

Every command supports `--help`. Errors go to standard error and return exit code 2; `doctor` returns 1 for a failed health check.

- `ctxdock init`: idempotently create configuration, project registry, record directories, and FTS5 database.
- `ctxdock save [--project ID] [--json OBJECT]`: save a JSON object. Stdin is preferred for multiline values. Required fields are `title` and `summary` (or `content`).
- `ctxdock find QUERY`: ranked level-1 results. Filters include `--category`, `--status`, `--limit`, and `--project`. `--detailed` adds level-2 fields, `--cross-project` is explicit, and `--max-chars` enforces a JSON budget.
- `ctxdock get ID [--summary]`: full record (level 3) or summary/rationale (level 2).
- `ctxdock list`: newest records for the current project. Supports category, status, ISO date, limit, and explicit cross-project filters.
- `ctxdock update ID`: accept changed fields as JSON. Include the previously read `expected_updated_at` for lost-update protection. Stable ID and revision history are retained.
- `ctxdock handoff`: with JSON, save current goal, completed work, decisions, files, blockers, and next actions; without JSON, return the newest active project handoff.
- `ctxdock rebuild`: reconstruct the index from JSON. A corrupt database is moved under `backups/` first.
- `ctxdock doctor`: check Python, home, database, FTS5, readable records, and skill installation.
- `ctxdock stats`: report local counts, bytes, sample latency, output size, and explicitly estimated tokens.
- `ctxdock install-skill` / `uninstall-skill`: manage only the agent skill files.

Statuses are `active`, `superseded`, and `archived`. Scopes are `project` and `shared`. Saving a record with `supersedes` marks the referenced indexed record superseded.

