from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest

from ctxdock.security import SecurityError
from ctxdock.storage import Store, bounded_json
from tests.helpers import TempHome


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = TempHome()
        self.store = Store(self.temp.path)
        self.store.init()

    def tearDown(self):
        self.temp.cleanup()

    def save(self, title="Database choice", summary="Use PostgreSQL for relational entities", project="alpha", **extra):
        return self.store.save({"title": title, "summary": summary, "category": "architecture", **extra}, project)[0]

    def test_first_and_repeated_initialization(self):
        first = self.store.init()
        second = self.store.init()
        self.assertTrue(first["initialized"] and second["initialized"])
        self.assertTrue((self.temp.path / "index.db").is_file())

    def test_save_get_and_human_readable_json(self):
        record = self.save()
        loaded = self.store.get(record["id"])
        self.assertEqual(loaded["summary"], record["summary"])
        text = Path(self.store.list_records("alpha")[0]["path"]).read_text(encoding="utf-8")
        self.assertIn('\n  "category"', text)

    def test_exact_duplicate_rejected_but_similar_allowed(self):
        self.save()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.save()
        second = self.save(summary="Use PostgreSQL 17 for relational entities")
        self.assertTrue(second["id"].startswith("mem-"))

    def test_find_relevant_information_and_symbols(self):
        expected = self.save()
        self.save("Frontend", "Use React and TypeScript", category="decision")
        results = self.store.find("PostgreSQL relational", "alpha")
        self.assertEqual(results[0]["id"], expected["id"])
        self.save("Language ABI", "Build the core with C++20", category="constraint")
        self.assertTrue(self.store.find("C++20", "alpha"))

    def test_missing_and_malformed_queries(self):
        self.save()
        self.assertEqual(self.store.find("nonexistentterm", "alpha"), [])
        with self.assertRaises(ValueError):
            self.store.find("+++", "alpha")

    def test_project_isolation_and_explicit_cross_project(self):
        alpha = self.save(project="alpha")
        beta = self.save("Beta database", "Use SQLite for the embedded beta database", project="beta")
        default = self.store.find("database", "alpha", limit=10)
        self.assertIn(alpha["id"], [row["id"] for row in default])
        self.assertNotIn(beta["id"], [row["id"] for row in default])
        crossed = self.store.find("database", "alpha", cross_project=True, limit=10)
        self.assertIn(beta["id"], [row["id"] for row in crossed])

    def test_shared_scope_is_intentionally_visible(self):
        shared = self.save("Shared convention", "All projects use semantic versioning", "alpha", scope="shared")
        results = self.store.find("semantic versioning", "beta")
        self.assertEqual(results[0]["id"], shared["id"])

    def test_update_preserves_id_and_revision_history(self):
        record = self.save()
        updated, _ = self.store.update(record["id"], {"summary": "Use SQLite for the local-only edition"}, record["updated_at"])
        self.assertEqual(updated["id"], record["id"])
        self.assertEqual(len(updated["revisions"]), 1)
        self.assertEqual(updated["revisions"][0]["summary"], record["summary"])
        with self.assertRaisesRegex(RuntimeError, "changed"):
            self.store.update(record["id"], {"summary": "stale"}, record["updated_at"])

    def test_superseded_record_ranks_after_active(self):
        old = self.save("Cache decision old", "Use Redis cache for sessions")
        new = self.save("Cache decision current", "Use Redis cache with a five minute TTL", supersedes=old["id"])
        results = self.store.find("Redis cache", "alpha", limit=10)
        self.assertEqual(results[0]["id"], new["id"])
        self.assertEqual(self.store.get(old["id"])["status"], "superseded")

    def test_concurrent_writes(self):
        self.store.project("concurrent")
        def write(number):
            return self.store.save({"title": f"Decision {number}", "summary": f"Unique concurrent value {number}", "category": "decision"}, "concurrent")[0]["id"]
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(write, range(30)))
        self.assertEqual(len(set(ids)), 30)
        self.assertEqual(len(self.store.list_records("concurrent", limit=100)), 30)

    def test_rebuild_after_database_deletion_and_corruption(self):
        record = self.save()
        self.store.db_path.unlink()
        self.assertEqual(self.store.rebuild(), 1)
        self.assertEqual(self.store.get(record["id"])["id"], record["id"])
        self.store.db_path.write_bytes(b"not a database")
        self.assertEqual(self.store.rebuild(), 1)
        self.assertTrue(list((self.temp.path / "backups").glob("index-corrupt-*.db")))

    def test_secret_detection_and_sensitive_warning(self):
        with self.assertRaises(SecurityError):
            self.save(summary="password = ultrasecretvalue")
        _record, warnings = self.store.save({"title": "Owner", "summary": "Ask dev@example.com before release"}, "alpha")
        self.assertIn("email address", warnings)

    def test_invalid_project_and_windows_compatible_path(self):
        with self.assertRaises(SecurityError):
            self.save(project="../escape")
        record = self.store.save({"title": "Windows path", "summary": r"Config is under C:\\work\\app\\settings.json"}, "win-project")[0]
        self.assertEqual(self.store.get(record["id"])["project_id"], "win-project")

    def test_compact_output_limit_is_valid_json(self):
        output = bounded_json({"large": "x" * 5000}, 180)
        self.assertLessEqual(len(output), 180)
        self.assertTrue(json.loads(output)["truncated"])

    def test_handoff_creation_and_retrieval(self):
        created = self.store.handoff({"current_goal": "Ship MVP", "completed_work": ["core"], "blockers": [], "next_actions": ["tests"]}, "alpha")
        latest = self.store.handoff(None, "alpha")
        self.assertEqual(latest["id"], created["id"])
        self.assertIn("Ship MVP", latest["summary"])

    def test_large_record_collection(self):
        for number in range(250):
            self.store.save({"title": f"Synthetic {number}", "summary": f"Component {number} uses protocol term{number}", "category": "fixture"}, "large")
        result = self.store.find("term249", "large")
        self.assertEqual(result[0]["title"], "Synthetic 249")


if __name__ == "__main__":
    unittest.main()

