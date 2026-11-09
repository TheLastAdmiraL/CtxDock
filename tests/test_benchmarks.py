from __future__ import annotations

import json
import unittest

from benchmarks.run_codex import parse_events, summarize


class BenchmarkParserTests(unittest.TestCase):
    def test_final_usage_event_is_used_without_cumulative_double_counting(self):
        events = "\n".join([
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 3}}),
            json.dumps({"type": "item.completed", "item": {"text": "PostgreSQL 17"}}),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 25, "cached_input_tokens": 5, "output_tokens": 7, "reasoning_output_tokens": 2}}),
        ])
        usage, response = parse_events(events)
        self.assertEqual(usage["input_tokens"], 25)
        self.assertEqual(usage["non_cached_input_tokens"], 20)
        self.assertEqual(usage["output_tokens"], 7)
        self.assertIn("PostgreSQL", response)

    def test_summary_reports_failures_and_medians(self):
        rows = [
            {"configuration": "ctxdock", "failure": False, "correct": True, "wall_seconds": 2.0, "retrieved_context_bytes": 100,
             "usage": {"input_tokens": 50, "cached_input_tokens": 10, "output_tokens": 5}},
            {"configuration": "ctxdock", "failure": False, "correct": False, "wall_seconds": 4.0, "retrieved_context_bytes": 120,
             "usage": {"input_tokens": 70, "cached_input_tokens": 20, "output_tokens": 9}},
        ]
        summary = summarize(rows)["ctxdock"]
        self.assertEqual(summary["median_input_tokens"], 60)
        self.assertEqual(summary["accuracy"], 0.5)


if __name__ == "__main__":
    unittest.main()
