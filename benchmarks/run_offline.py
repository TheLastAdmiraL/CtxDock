#!/usr/bin/env python3
"""Reproducible, network-free CtxDock retrieval benchmark."""

from __future__ import annotations

import argparse
import json
import random
import shutil
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ctxdock.storage import Store  # noqa: E402

SEED = 20261109
TOPICS = ["authentication", "database", "caching", "logging", "deployment", "payments", "search", "testing"]


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def run_size(size: int, work_root: Path) -> dict[str, object]:
    home = work_root / f"library-{size}"
    shutil.rmtree(home, ignore_errors=True)
    store = Store(home)
    store.init()
    rng = random.Random(SEED + size)
    expected: dict[str, str] = {}
    tracemalloc.start()
    started = time.perf_counter()
    for number in range(size):
        topic = TOPICS[number % len(TOPICS)]
        project = f"project-{number % 5}"
        marker = f"fact{number:05d}"
        record, _ = store.save({
            "title": f"{topic.title()} decision {number}",
            "summary": f"The finalized {topic} constraint is {marker}; synthetic value {rng.randrange(1_000_000)}.",
            "rationale": "Synthetic benchmark fixture with a known relevant identifier.",
            "category": "decision",
            "tags": [topic, "benchmark"],
            "status": "superseded" if number % 97 == 0 else "active",
        }, project)
        expected[marker] = record["id"]
    save_seconds = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    query_numbers = random.Random(SEED).sample(range(size), min(100, size))
    for number in query_numbers[:10]:
        store.find(f"fact{number:05d}", f"project-{number % 5}")
    latencies: list[float] = []
    returned_bytes: list[int] = []
    true_positive = 0
    returned_count = 0
    obsolete_count = 0
    isolation_violations = 0
    for number in query_numbers:
        marker = f"fact{number:05d}"
        project = f"project-{number % 5}"
        start = time.perf_counter()
        rows = store.find(marker, project, limit=5)
        latencies.append((time.perf_counter() - start) * 1000)
        encoded = json.dumps(rows, ensure_ascii=False).encode("utf-8")
        returned_bytes.append(len(encoded))
        ids = {row["id"] for row in rows}
        true_positive += int(expected[marker] in ids)
        returned_count += len(rows)
        obsolete_count += sum(row["status"] != "active" for row in rows)
        isolation_violations += sum(row["project_id"] != project and row["scope"] != "shared" for row in rows)
    query_count = len(query_numbers)
    precision = true_positive / returned_count if returned_count else 0.0
    recall = true_positive / query_count if query_count else 0.0
    index_bytes = sum(path.stat().st_size for path in home.glob("index.db*"))
    result = {
        "records": size,
        "seed": SEED,
        "save_and_index_seconds": round(save_seconds, 4),
        "records_per_second": round(size / save_seconds, 2),
        "index_bytes": index_bytes,
        "peak_python_memory_bytes": peak,
        "queries": query_count,
        "search_latency_ms_p50": round(percentile(latencies, 0.50), 4),
        "search_latency_ms_p95": round(percentile(latencies, 0.95), 4),
        "mean_results": round(returned_count / query_count, 3),
        "mean_output_bytes": round(statistics.mean(returned_bytes), 2),
        "estimated_mean_tokens": round(statistics.mean(returned_bytes) / 4, 2),
        "token_note": "Estimated as UTF-8 bytes / 4; not model-reported usage.",
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "obsolete_results": obsolete_count,
        "project_isolation_violations": isolation_violations,
    }
    shutil.rmtree(home, ignore_errors=True)
    return result


def markdown(results: list[dict[str, object]]) -> str:
    lines = [
        "# CtxDock offline benchmark", "", f"Fixed random seed: `{SEED}`. No network or model calls were used.", "",
        "| Records | Save/index s | Search p50 ms | Search p95 ms | Index bytes | Est. tokens | Precision | Recall | Isolation violations |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in results:
        lines.append(f"| {row['records']} | {row['save_and_index_seconds']} | {row['search_latency_ms_p50']} | {row['search_latency_ms_p95']} | {row['index_bytes']} | {row['estimated_mean_tokens']} | {row['precision']} | {row['recall']} | {row['project_isolation_violations']} |")
    lines += ["", "Token values are rough local estimates, not reported model usage. Results depend on hardware and filesystem behavior.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", nargs="+", type=int, default=[100, 1000, 10000])
    parser.add_argument("--output-dir", type=Path, default=ROOT / "benchmarks" / "results")
    args = parser.parse_args()
    if any(size < 1 for size in args.sizes):
        parser.error("sizes must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    work_root = ROOT / ".benchmark-tmp"
    work_root.mkdir(exist_ok=True)
    try:
        results = [run_size(size, work_root) for size in args.sizes]
    finally:
        shutil.rmtree(work_root, ignore_errors=True)
    payload = {"schema_version": 1, "benchmark": "offline", "results": results}
    (args.output_dir / "offline.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "offline.md").write_text(markdown(results), encoding="utf-8")
    print(markdown(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

