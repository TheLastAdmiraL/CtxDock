# Benchmarking methodology

Benchmarks answer two separate questions: how well local retrieval works, and how model usage changes in controlled Codex tasks. Neither proves lower financial cost or universally better answers.

## Offline retrieval

```console
python benchmarks/run_offline.py
python benchmarks/run_offline.py --sizes 100
```

The default fixed-seed run creates isolated synthetic libraries of 100, 1,000, and 10,000 records. It measures save/index wall time, throughput, FTS index bytes, Python peak allocation, warm search p50/p95 latency, returned records/bytes, estimated tokens, exact-ID precision/recall, obsolete results, and project-isolation violations. It makes no network or model calls. JSON and Markdown are written under ignored `benchmarks/results/`.

The token estimate is UTF-8 bytes divided by four. It is explicitly not a tokenizer result. Filesystem, antivirus, SQLite build, Python version, and hardware affect measurements. Exact unique markers make relevance ground truth reproducible but simpler than natural developer language.

## Codex usage

```console
python benchmarks/run_codex.py --dry-run
python benchmarks/run_codex.py --live --runs 3 --max-runs 150
```

Dry-run is the default. `--live` deliberately launches model requests, prints the expected count first, and obeys a maximum. The runner uses ten synthetic scenarios: architecture, bug fix, changed requirement, superseded decision, handoff, ambiguity, similar projects, conflict, missing knowledge, and exact constraint.

Each scenario compares:

- `no_memory`: unsupported continuity baseline, not a token-savings claim;
- `manual_full`: relevant fact inside long synthetic history;
- `ctxdock`: a fresh run instructed to perform one local search;
- `compact_manual`: ideal concise fact baseline;
- `skill_idle`: installed/mentioned overhead without invocation.

Keep the same model, reasoning effort, project state, and repetitions. `codex exec --json` events are parsed; the final `turn.completed` usage object is used to avoid double-counting cumulative events. Reports distinguish total, cached, and calculated non-cached input; output and reasoning tokens; wall time; retrieved bytes; search count; failures; and exact-fact correctness. Multiple runs are summarized by medians. Event schema changes appear as failures instead of silently substituting estimates.

The runner uses synthetic facts only and temporary CtxDock storage. It does not upload private memories. Review prompts, Codex version, account limits, model nondeterminism, cache behavior, and correctness scoring before interpreting relative changes.

