# CtxDock

**Save what matters. Recall anywhere.**

CtxDock is a local-first Agent Skill for carrying curated project knowledge, architectural decisions, constraints, and session handoffs between coding-agent sessions. It uses 100% Python standard library (`sqlite3`, `json`, `pathlib`) with zero cloud dependencies, no network calls, and no embedding APIs.

---

# **RECOMMENDED INSTALLATION: COPY TO YOUR CODING AGENT**

Simply copy and paste this single instruction into your AI coding agent (Antigravity, Claude Code, Cursor, OpenAI Codex, or Gemini CLI):

```text
Install the CtxDock skill from https://github.com/TheLastAdmiraL/CtxDock
```

> **You can install it using `git clone` but the config requires questions that you will need to answer. We recommend using the instruction given to the agent. If you do `git clone` then you can set it up from your agent by giving these instructions:**
>
> 1. Clone the repository:
>    ```bash
>    git clone https://github.com/TheLastAdmiraL/CtxDock.git
>    cd CtxDock
>    ```
> 2. Open your coding agent in the directory and say:
>    ```text
>    Set up CtxDock from this repository
>    ```
> 3. Your agent will ask you two simple questions in chat:
>    * **Scope**: Do you want **Project-Specific** memory (`.ctxdock/` inside this repo) or **Global** memory (`~/.ctxdock/` across all projects)?
>    * **Agents**: Which agents should have access? (`Antigravity`, `Claude Code`, `Cursor`, `OpenAI Codex`, `Gemini CLI`, or `All`)
>
> Your agent will automatically configure the skill hooks with **zero pip dependencies**.

---

## Context Footprint & Token Economics

In multi-session agent workflows, restoring context usually means re-pasting conversation logs or having the agent re-read multiple source files. As a project grows, this burns thousands to tens of thousands of tokens every single session.

CtxDock replaces transcript-dumping with **compact, bounded progressive retrieval**.

### Verified Payload Measurements (Deterministic & Offline)

All values below are measured directly from CtxDock's standard-library execution path:

| Retrieval Stage | Real Payload Size | Measured Tokens | What It Contains |
| :--- | :---: | :---: | :--- |
| **Idle System Prompt (`SKILL.md`)** | 1,825 bytes | **~450 tokens** | Lean instructions loaded once into agent context |
| **Locator Search (`ctxdock find`)** | ~780 bytes | **~196 tokens** | Top-3 ranked matches with IDs, titles, and snippets |
| **Precision Detail (`get --summary`)** | ~430 bytes | **~110 tokens** | Target decision, rationale, and metadata |
| **Session Continuity (`handoff`)** | ~900 bytes | **~230 tokens** | Current goal, completed items, blockers, next actions |

*Token estimates are calculated as UTF-8 bytes divided by 4 across libraries of 100 to 10,000 records. They represent deterministic output boundaries, not reported model usage.*

---

### Progressive Retrieval Architecture

CtxDock operates in three lightweight stages so that an agent never ingests more context than necessary:

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Stage 1: Ultra-Lean Idle Footprint (~450 tokens)                                │
│ The skill definition loaded into the agent's system prompt is under 40 lines.   │
│ It introduces minimal baseline overhead and zero external dependencies.        │
└───────────────────────────────────────┬─────────────────────────────────────────┘
                                        │ (When agent needs past context)
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Stage 2: Fast Locator Search (~196 tokens)                                      │
│ Agent calls: python scripts/ctxdock.py find "<query>"                           │
│ Returns only 1-line locator tuples: id, title, category, status, and snippet.   │
│ Strips all full summaries, rationales, and revision logs.                       │
└───────────────────────────────────────┬─────────────────────────────────────────┘
                                        │ (If specific details are needed)
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Stage 3: Targeted Precision Detail (~110 tokens)                                │
│ Agent calls: python scripts/ctxdock.py get <id> --summary                       │
│ Returns strictly the single relevant decision and rationale.                    │
│ Total turn context: ~300 tokens (vs. thousands of tokens for full file rescans).│
└─────────────────────────────────────────────────────────────────────────────────┘
```

> [!NOTE]
> **Token Economics Notice**: Actual token savings depend entirely on what context you would have provided otherwise. CtxDock bounds active retrieval payloads to ~$O(1)$ tool calls, but does not claim guaranteed financial savings over a concise, hand-crafted prompt.

---

### Benchmarking Tools

CtxDock provides two independent benchmark suites:

1. **Deterministic Offline Benchmark (No Network, No API Keys)**:
   Measures local FTS5 indexing speed, search latency, index size, and payload bytes across 100, 1,000, and 10,000 records:
   ```bash
   python benchmarks/run_offline.py --sizes 100 1000 10000
   ```
2. **Empirical Live Model Benchmark (Opt-In Codex Harness)**:
   Executes live model requests via `codex exec --json` to capture actual `usage.input_tokens` events across 10 real-world scenarios and 5 configurations (`no_memory`, `manual_full`, `ctxdock`, `compact_manual`, `skill_idle`):
   ```bash
   python benchmarks/run_codex.py --dry-run
   python benchmarks/run_codex.py --live --runs 3 --max-runs 150
   ```
   *Live benchmarks consume model credits and require deliberate `--live`. See [benchmarking methodology](docs/benchmarking.md).*

---

## Storage Architecture: Project-Specific vs. Global

CtxDock automatically detects where to store and read memories:

### 1. Project-Specific (Local) Mode
* **Location**: `<repo>/.ctxdock/`
* **Team Sharing**: JSON records in `.ctxdock/records/` can be committed to Git so anyone on your team (and their agents) shares the exact same architectural history.
* **Safe Defaults**: SQLite search indices (`*.db`, `*.db-wal`) are automatically `.gitignore`'d and safely rebuilt locally on demand with zero merge conflicts.
* **Boundary**: Memories never leave the repository.

### 2. Global Mode
* **Location**: `~/.ctxdock/` (or `%USERPROFILE%\.ctxdock` on Windows).
* **Cross-Project Access**: Accessible by all agents across any project on your computer.
* **Isolation**: Records remain project-isolated by default, with explicit `--scope shared` for global developer preferences and rules.

---

## Agent Integration Hooks

When installed, CtxDock integrates into each agent's native discovery workflow without requiring global environment modifications:

| Agent | Global Hook Location | Project-Specific Hook Location |
| :--- | :--- | :--- |
| **Antigravity** | `~/.agents/skills/ctxdock/` | `<repo>/.agent/skills/ctxdock/` |
| **OpenAI Codex** | `~/.agents/skills/ctxdock/` | `<repo>/.agents/skills/ctxdock/` |
| **Cursor** | `~/.cursor/rules/ctxdock.mdc` | `<repo>/.cursor/rules/ctxdock.mdc` |
| **Claude Code** | Global `~/.claude/` rule | Appends pointer to `<repo>/CLAUDE.md` |
| **Gemini CLI** | `~/.gemini/skills/ctxdock/` | `<repo>/.gemini/skills/ctxdock/` |

---

## First Use & Usage Examples

Agents run the bundled standard-library runner directly:

### 1. Search Historical Knowledge
```bash
python .agent/skills/ctxdock/scripts/ctxdock.py find "database architecture"
python .agent/skills/ctxdock/scripts/ctxdock.py get mem-0123456789abcdef --summary
```

### 2. Record a Finalized Decision
```bash
printf '%s' '{"title":"Database Engine","summary":"Use PostgreSQL 17 for multi-tenant data.","category":"architecture","rationale":"Strong relational isolation.","tags":["db","postgres"]}' | python .agent/skills/ctxdock/scripts/ctxdock.py save
```

### 3. Session Handoffs
```bash
# Record handoff at end of session:
printf '%s' '{"current_goal":"Ship auth MVP","completed_work":["tokens","schema"],"blockers":[],"next_actions":["verify tests"]}' | python .agent/skills/ctxdock/scripts/ctxdock.py handoff

# Retrieve handoff at start of next session:
python .agent/skills/ctxdock/scripts/ctxdock.py handoff
```

---

## Security, Boundaries & Storage Reliability

- **Secret Detection**: Rejects commits containing private keys, AWS tokens, GitHub credentials, JWTs, API keys, or raw password assignments while permitting standard placeholders (`<redacted>`, `[removed]`, `${PASSWORD}`, `********`).
- **Record Limits**: Hard limits prevent unbounded disk consumption (Title: 512 chars; Summary: 64 KB; Rationale: 64 KB; Input: 256 KB; Max 64 tags).
- **Windows File Contention Protection**: Atomic JSON updates employ 5 exponential backoff retries (20ms to 320ms) to transparently survive transient Windows antivirus/indexer `PermissionError` locking.
- **Database Migrations (`SCHEMA_VERSION = 2`)**: SQLite upgrades automatically create pre-migration backups in `backups/` and checkpoint WAL logs atomically via SQLite's native backup API.
- **Scoped Statistics**: `ctxdock stats` reports storage and latency metrics strictly scoped to the active project by default; `--cross-project` provides explicit global visibility.

---

## Retrieval Latency Benchmarks

Offline retrieval benchmarks (tested with fixed seed `20261109`, 0 network calls, 0 model dependencies):

| Records | Save/index s | Search p50 ms | Search p95 ms | Index bytes | Est. tokens | Precision | Recall | Isolation violations |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 7.81s | 60.89 ms | 69.54 ms | 159 KB | 196 | 1.0000 | 1.0000 | 0 |
| 1,000 | 79.04s | 60.14 ms | 66.98 ms | 1.10 MB | 197 | 1.0000 | 1.0000 | 0 |
| 10,000 | 835.78s | 52.21 ms | 65.28 ms | 10.49 MB | 197 | 1.0000 | 1.0000 | 0 |

---

## Platform Status & CI Matrix

| Platform | Automated CI Status | Target Python Versions |
| :--- | :---: | :---: |
| **Ubuntu Linux** | Passing | 3.11, 3.12, 3.13 |
| **Windows** | Passing | 3.11, 3.12, 3.13 |
| **macOS** | Passing | 3.11, 3.12, 3.13 |

---

## Development

```console
# Run test suite
python -m unittest discover -s tests -v

# Check skill definition synchronization
python tools/sync_skill.py --check

# Run offline retrieval benchmark
python benchmarks/run_offline.py --sizes 25
```

CtxDock is open source under the [MIT License](LICENSE).
