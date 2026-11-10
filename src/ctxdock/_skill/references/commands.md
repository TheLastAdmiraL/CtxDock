# CtxDock command reference

- `ctxdock init` — initialize `~/.ctxdock` (or `CTXDOCK_HOME`).
- `ctxdock save [--project ID]` — accept a JSON record on stdin.
- `ctxdock find QUERY [--project ID] [--cross-project] [--detailed]` — ranked FTS5 search.
- `ctxdock get ID [--summary]` — retrieve one stable record.
- `ctxdock list [--category NAME] [--status STATUS]` — list the current project.
- `ctxdock update ID` — accept JSON changes on stdin; include `expected_updated_at` for optimistic concurrency.
- `ctxdock handoff` — retrieve the latest handoff; pipe JSON fields to create one.
- `ctxdock rebuild`, `ctxdock doctor`, `ctxdock stats` — maintenance and diagnostics.

Project records are isolated by default. `--cross-project` is an explicit disclosure boundary. Shared-scope records are intentionally visible across projects. Use `--max-chars` when a strict context budget is needed.

