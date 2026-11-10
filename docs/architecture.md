# Architecture

CtxDock separates canonical storage, derived search state, and agent instructions.

1. `projects.py` identifies a Git root and derives a path-based project ID, unless the caller supplies a stable explicit ID.
2. `records.py` validates and normalizes knowledge, enforces payload bounds (512-char title, 64 KB summary and rationale, 64 tags, 256 KB input), computes SHA-256 hashes, and rejects obvious secrets.
3. `storage.py` writes readable JSON atomically under the global home. It coordinates SQLite transactions, revision history, handoffs, recovery, and statistics.
4. `index.py` maintains a versioned SQLite schema (with a `metadata` table and automated migrations) and FTS5 index. Search filters project scope before returning compact results and ranks active records first.
5. `cli.py` exposes predictable JSON input/output and nonzero error codes.
6. `skill/ctxdock/` teaches an agent when and how to use the CLI without loading the library into its prompt.

JSON records are authoritative. `index.db` is disposable derived state, so `ctxdock rebuild` scans records and recreates it. Record IDs remain stable through updates; each update embeds the previous state in `revisions`. A SHA-256 hash over meaningful content prevents exact duplicates within a project and scope.

SQLite uses WAL, full synchronization, transactions, parameterized values, and a 30-second busy timeout. JSON is written to a sibling temporary file, flushed, and atomically replaced. Update callers can supply `expected_updated_at` to prevent a stale writer from silently overwriting newer knowledge.

FTS queries are converted into quoted word terms rather than interpolated as SQL or raw FTS syntax. This safely handles punctuation and programming symbols, though v1 is lexical rather than semantic. Search never reads all records into the model context.

Security boundaries are local-account boundaries, not encryption boundaries. The project filter prevents accidental logical leakage; operating-system permissions protect files where supported. `shared` scope and `--cross-project` deliberately cross normal project isolation.

