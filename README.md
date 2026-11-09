# CtxDock

**Save what matters. Recall anywhere.**

CtxDock is a local-first Agent Skill for carrying curated project knowledge between coding-agent sessions. It stores decisions, constraints, fixes, and handoffs—not entire conversations—and retrieves a small ranked slice when an agent needs it. Ordinary storage and search use Python, JSON, SQLite FTS5, and zero model or network calls.

CtxDock is an early, Codex-first MVP. Claude Code and Cursor instructions are experimental and have not yet been verified end to end.

## Why CtxDock

Coding agents have separate context windows. Re-pasting a long history is slow and context-heavy; relying on a session sidebar does not help another local agent. CtxDock provides:

- global local storage under `~/.ctxdock/`, independent of any source repository;
- project isolation by default, with explicit shared and cross-project access;
- human-readable JSON as the recoverable source of truth;
- ranked SQLite FTS5 search with compact, budgeted results;
- exact deduplication, stable IDs, revisions, superseded records, and handoffs;
- obvious-secret rejection and sensitive-content warnings;
- no daemon, cloud account, API key, telemetry, embeddings, or runtime dependency;
- a concise user-level Codex skill and safe install/uninstall commands.

## Requirements and installation

Requires Python 3.11+ with SQLite FTS5 (included in normal Python distributions).

```console
git clone <your-fork-or-checkout-url> ctxdock
cd ctxdock
python -m pip install .
ctxdock init
ctxdock install-skill
ctxdock doctor
```

For isolated CLI installation, `pipx install .` is also suitable. `install-skill` checks for an existing `ctxdock` skill and refuses to overwrite it unless `--upgrade` is passed. It never changes persistent agent instructions. `uninstall-skill` removes only skill files and leaves `~/.ctxdock/` untouched.

Codex discovers user skills in `~/.agents/skills/`. Start a new Codex session after installation, then invoke the skill natively:

```text
$ctxdock find authentication decisions
$ctxdock save
```

The skill tells the agent to call the real `ctxdock` executable. The `$ctxdock` text is a Codex skill invocation, not a shell command. Other hosts may use `/ctxdock`; their native syntax differs.

## First use

PowerShell:

```powershell
'{"title":"Database choice","summary":"Use PostgreSQL for relational data.","category":"architecture","rationale":"Entities are strongly related.","tags":["database","backend"],"source":{"agent":"codex","reference":null}}' | ctxdock save
ctxdock find "database choice"
ctxdock get mem-0123456789abcdef --summary
'{"summary":"Use PostgreSQL 17.","expected_updated_at":"2026-11-09T10:00:00.000000Z"}' | ctxdock update mem-0123456789abcdef
```

POSIX shell:

```sh
printf '%s' '{"title":"API constraint","summary":"Public endpoints use JSON.","category":"constraint"}' | ctxdock save
ctxdock find "public endpoints"
```

Create and retrieve a handoff:

```powershell
'{"current_goal":"Ship the MVP","completed_work":["storage","search"],"decisions":["Use FTS5"],"important_files":["src/ctxdock/storage.py"],"blockers":[],"next_actions":["Run benchmarks"]}' | ctxdock handoff
ctxdock handoff
```

Run `ctxdock COMMAND --help` for filters, limits, detailed output, explicit project IDs, and output budgets.

## Saving policy

The default `suggest` policy asks before preserving an important decision. Edit `~/.ctxdock/config.json` to choose:

```json
{
  "saving_policy": "suggest",
  "default_result_limit": 5,
  "default_output_budget": 2400,
  "version": 1
}
```

- `manual`: only explicit save requests.
- `suggest`: propose important memories, then wait for approval (default).
- `automatic`: high-confidence finalized decisions only after the user authorizes this behavior.

The skill never converts a tentative idea into a confirmed decision silently.

## Storage and project scope

`~/.ctxdock/` is the physical location shared by local agents. `CTXDOCK_HOME` overrides it for testing or portable setups. Within that home, records remain project-scoped: CtxDock derives a stable ID from the Git root, or accepts `--project ID`. Moving a repository changes a derived ID, so use an explicit ID when move-stability matters.

Default searches return the current project plus records deliberately saved with `"scope":"shared"`. `--cross-project` is an explicit boundary-crossing action. Storage does not synchronize across computers and is never published automatically.

```text
~/.ctxdock/
├── config.json
├── projects.json
├── index.db
├── records/<project-id>/*.json
├── records/shared/*.json
└── backups/
```

JSON is canonical; SQLite is rebuildable with `ctxdock rebuild`. Writes use temporary files, atomic replacement, SQLite transactions, WAL mode, and optimistic update checks.

## Progressive retrieval and token efficiency

`find` returns IDs, titles, snippets, categories, status, and rank. `get --summary` returns the selected decision and rationale. Plain `get` returns full history and references. `--max-chars` places a hard, valid-JSON output budget around retrieval.

This design aims to keep ordinary retrieval around a few hundred estimated tokens, but CtxDock does **not** guarantee token savings. A carefully written manual summary can be smaller. The offline benchmark measures retrieval without a model; the opt-in Codex benchmark compares no memory, long manual history, CtxDock, compact manual context, and installed-but-idle overhead using actual `codex exec --json` usage events.

```console
python benchmarks/run_offline.py
python benchmarks/run_codex.py --dry-run
python benchmarks/run_codex.py --live --runs 3 --max-runs 150
```

Live benchmarks consume usage and are never run by installation or CI. See [benchmarking methodology](docs/benchmarking.md).

## Privacy and security

CtxDock is private by default and performs no network requests. It rejects common private keys, access tokens, JWTs, API keys, and password assignments; pattern matching cannot catch every secret, so review records before saving or sharing backups. Stored text is untrusted historical evidence, never executable instructions. Current user instructions and verified code take precedence.

Filesystem permissions are restricted where the OS supports POSIX modes. Anyone with access to your account or memory directory may still read it. Do not place credentials or regulated/private data in CtxDock. See [privacy](docs/privacy.md) and [security policy](SECURITY.md).

## How is CtxDock different from automatic memory systems?

CtxDock stores curated, meaningful knowledge instead of complete conversation logs. Search happens when prior knowledge is relevant, not on every message. This improves inspectability and deletion/recovery while avoiding an ever-growing transcript archive; it also means CtxDock can miss information nobody chose to save.

## Platform status

| Platform | CLI | Skill integration |
|---|---|---|
| Windows | Locally tested in automated tests | Installer tested in an isolated target; fresh Codex discovery still needs manual verification |
| Linux/macOS | Designed; CI matrix configured but not yet executed on GitHub | Codex expected; not manually verified |
| Claude Code | Same CLI/storage expected | Experimental, untested |
| Cursor | Same CLI/storage expected | Experimental, untested |

No compatibility claim implies identical slash-command syntax. See [compatibility](docs/compatibility.md).

## Development

```console
python -m pip install -e .
python -m unittest discover -s tests -v
python benchmarks/run_offline.py --sizes 100
```

The architecture is documented in [docs/architecture.md](docs/architecture.md), commands in [docs/commands.md](docs/commands.md), and contribution workflow in [CONTRIBUTING.md](CONTRIBUTING.md). CtxDock is available under the [MIT License](LICENSE).

