#!/usr/bin/env python3
"""Explicitly opt-in Codex CLI token-usage benchmark using synthetic facts."""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ctxdock.storage import Store  # noqa: E402

SCENARIOS = [
    ("architecture", "Which database was finalized?", "PostgreSQL 17", "The team finalized PostgreSQL 17 after comparing three databases."),
    ("bug_fix", "What fixed duplicate webhook processing?", "idempotency key", "Duplicate webhooks were fixed by enforcing an idempotency key."),
    ("changed_requirement", "What is the current retention period?", "30 days", "Retention changed from 90 days to 30 days."),
    ("superseded", "Which cache is current?", "Valkey", "Redis was superseded; the active cache decision is Valkey."),
    ("handoff", "What should the next agent do?", "migration tests", "The next action in the handoff is to add migration tests."),
    ("ambiguous", "Which port does the worker use?", "7312", "The background worker, not the web server, uses port 7312."),
    ("similar_projects", "What framework does project Atlas use?", "Django", "Project Atlas uses Django; project Apollo uses FastAPI."),
    ("conflict", "Which API version is active?", "v3", "An old note says v2, but the finalized active API version is v3."),
    ("missing", "What color was never decided?", "unknown", "No interface color decision exists; answer unknown rather than guessing."),
    ("constraint", "What exact Python floor is required?", "Python 3.11", "The exact runtime floor is Python 3.11."),
]
CONFIGS = ("no_memory", "manual_full", "ctxdock", "compact_manual", "skill_idle")


def parse_events(stdout: str) -> tuple[dict[str, int], str]:
    usages: list[dict[str, Any]] = []
    response_parts: list[str] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usages.append(event["usage"])
        if event.get("type") in {"item.completed", "message.completed"}:
            item = event.get("item", event)
            text = item.get("text") or item.get("content")
            if isinstance(text, str):
                response_parts.append(text)
    usage = usages[-1] if usages else {}
    total = int(usage.get("input_tokens", 0))
    cached = int(usage.get("cached_input_tokens", 0))
    parsed = {
        "input_tokens": total,
        "cached_input_tokens": cached,
        "non_cached_input_tokens": max(0, total - cached),
        "output_tokens": int(usage.get("output_tokens", 0)),
        "reasoning_output_tokens": int(usage.get("reasoning_output_tokens", 0)),
    }
    return parsed, "\n".join(response_parts)


def prompt_for(config: str, scenario: str, question: str, fact: str, full_history: str, home: Path) -> str:
    base = f"Answer this synthetic evaluation question concisely. Question: {question}"
    if config == "manual_full":
        return f"{base}\nSynthetic project history:\n{full_history}"
    if config == "compact_manual":
        return f"{base}\nRelevant curated fact: {fact}"
    if config == "ctxdock":
        return f"{base}\nUse the local CtxDock CLI to retrieve the answer. CTXDOCK_HOME is {home}. Run: ctxdock find \"{scenario}\" --project benchmark --detailed"
    if config == "skill_idle":
        return f"{base}\nCtxDock is installed, but do not invoke it for this question. No prior project fact is provided."
    return base


def summarize(results: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    summary: dict[str, dict[str, float]] = {}
    for config in CONFIGS:
        rows = [row for row in results if row["configuration"] == config and not row["failure"]]
        if not rows:
            summary[config] = {"successful_runs": 0, "failure_count": sum(row["configuration"] == config for row in results)}
            continue
        summary[config] = {
            "successful_runs": len(rows),
            "failure_count": sum(row["configuration"] == config and row["failure"] for row in results),
            "median_input_tokens": statistics.median(row["usage"]["input_tokens"] for row in rows),
            "median_cached_tokens": statistics.median(row["usage"]["cached_input_tokens"] for row in rows),
            "median_output_tokens": statistics.median(row["usage"]["output_tokens"] for row in rows),
            "median_wall_seconds": statistics.median(row["wall_seconds"] for row in rows),
            "median_retrieved_context_bytes": statistics.median(row["retrieved_context_bytes"] for row in rows),
            "accuracy": sum(row["correct"] for row in rows) / len(rows),
        }
    return summary


def summary_markdown(summary: dict[str, dict[str, float]]) -> str:
    lines = ["# Codex usage benchmark", "", "All token counts are actual values from `turn.completed`; context bytes are local measurements.", "",
             "| Configuration | Input tokens | Output tokens | Cached tokens | Accuracy | Execution s | Retrieved bytes | Failures |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for config in CONFIGS:
        row = summary[config]
        if not row.get("successful_runs"):
            lines.append(f"| {config} | n/a | n/a | n/a | n/a | n/a | n/a | {row['failure_count']} |")
        else:
            lines.append(f"| {config} | {row['median_input_tokens']} | {row['median_output_tokens']} | {row['median_cached_tokens']} | {row['accuracy']:.3f} | {row['median_wall_seconds']} | {row['median_retrieved_context_bytes']} | {row['failure_count']} |")
    manual = summary.get("manual_full", {})
    dock = summary.get("ctxdock", {})
    if manual.get("median_input_tokens") and dock.get("median_input_tokens") is not None:
        change = (dock["median_input_tokens"] - manual["median_input_tokens"]) / manual["median_input_tokens"] * 100
        lines += ["", f"CtxDock median input-token change versus full manual context: **{change:+.2f}%**."]
    lines += ["", "Fewer tokens do not necessarily mean lower cost or better output quality.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Actually run Codex; consumes model usage")
    parser.add_argument("--dry-run", action="store_true", help="Print the run plan (default)")
    parser.add_argument("--runs", type=int, default=1, help="Repetitions per scenario/configuration")
    parser.add_argument("--max-runs", type=int, default=100)
    parser.add_argument("--model")
    parser.add_argument("--reasoning-effort")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks" / "results" / "codex.json")
    args = parser.parse_args()
    planned = len(SCENARIOS) * len(CONFIGS) * args.runs
    print(f"Planned Codex model runs: {planned} ({len(SCENARIOS)} scenarios × {len(CONFIGS)} configurations × {args.runs})")
    if planned > args.max_runs:
        parser.error(f"planned runs exceed --max-runs={args.max_runs}")
    if not args.live:
        print("Dry run only. Pass --live deliberately to execute model calls.")
        return 0
    if not shutil.which("codex"):
        parser.error("codex executable not found")

    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="ctxdock-live-benchmark-") as directory:
        home = Path(directory) / "memory"
        store = Store(home)
        store.init()
        for name, _question, _expected, fact in SCENARIOS:
            store.save({"title": name, "summary": fact, "category": "benchmark", "tags": [name]}, "benchmark")
        distractors = "\n".join(f"Historical note {n}: unrelated synthetic detail {n}." for n in range(100))
        for repetition in range(args.runs):
            for name, question, expected, fact in SCENARIOS:
                for config in CONFIGS:
                    prompt = prompt_for(config, name, question, fact, f"{distractors}\n{fact}", home)
                    command = ["codex", "exec", "--json"]
                    if args.model:
                        command += ["--model", args.model]
                    if args.reasoning_effort:
                        command += ["--config", f'model_reasoning_effort="{args.reasoning_effort}"']
                    command.append(prompt)
                    started = time.perf_counter()
                    proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
                    usage, response = parse_events(proc.stdout)
                    results.append({
                        "scenario": name, "configuration": config, "run": repetition + 1,
                        "model": args.model, "reasoning_effort": args.reasoning_effort,
                        "wall_seconds": round(time.perf_counter() - started, 3),
                        "retrieved_context_bytes": len(fact.encode()) if config in {"ctxdock", "compact_manual"} else (len((distractors + fact).encode()) if config == "manual_full" else 0),
                        "search_operations": 1 if config == "ctxdock" else 0,
                        "correct": expected.lower() in response.lower(),
                        "expected_fact": expected, "usage": usage,
                        "exit_code": proc.returncode, "failure": proc.returncode != 0 or not usage,
                    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    summary = summarize(results)
    args.output.write_text(json.dumps({"schema_version": 1, "usage_source": "codex exec --json turn.completed", "summary": summary, "results": results}, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(summary_markdown(summary), encoding="utf-8")
    print(f"Wrote {args.output}. Actual usage values are distinct from local context-size estimates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
