# CtxDock command reference

- `python scripts/ctxdock.py init` — initialize storage safely under `~/.ctxdock` (or `CTXDOCK_HOME`).
- `python scripts/ctxdock.py save [--project ID]` — save a structured knowledge record from JSON on stdin.
- `python scripts/ctxdock.py find QUERY [--project ID] [--cross-project] [--detailed] [--limit N]` — ranked FTS5 search with BM25 relevance.
- `python scripts/ctxdock.py get ID [--summary]` — retrieve a record by stable ID.
- `python scripts/ctxdock.py list [--project ID] [--category NAME] [--status STATUS] [--limit N]` — list records for the project.
- `python scripts/ctxdock.py update ID` — update an existing record while preserving revision history.
- `python scripts/ctxdock.py handoff` — create or retrieve the newest active handoff for the project.
- `python scripts/ctxdock.py rebuild` — rebuild the SQLite index from canonical JSON files.
- `python scripts/ctxdock.py doctor` — inspect storage, SQLite FTS5, permissions, and records.
- `python scripts/ctxdock.py stats [--cross-project]` — display storage, latency, output size, and estimated tokens.

Project records are isolated by default. `--cross-project` is an explicit boundary-crossing flag. Shared records (`"scope": "shared"`) are intentionally visible across projects.
