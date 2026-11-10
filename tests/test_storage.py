from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest
from unittest import mock

from ctxdock.security import SecurityError, ensure_within, _normalize_path
from ctxdock.storage import Store, _atomic_json, bounded_json
from ctxdock import index
from ctxdock.records import (
    MAX_TITLE_CHARS,
    MAX_SUMMARY_CHARS,
    MAX_RATIONALE_CHARS,
    MAX_SOURCE_REFERENCE_CHARS,
    MAX_TAGS,
    MAX_TAG_CHARS,
    MAX_INPUT_CHARS,
)
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


    def test_atomic_replace_retries_then_succeeds(self):
        target = self.temp.path / "retry_test.json"
        real_replace = os.replace
        calls = 0

        def flaky_replace(src, dst):
            nonlocal calls
            calls += 1
            if calls < 3:
                raise PermissionError("Access denied temporarily")
            return real_replace(src, dst)

        with mock.patch("ctxdock.storage.os.replace", side_effect=flaky_replace), mock.patch("ctxdock.storage.time.sleep"):
            _atomic_json(target, {"status": "ok"})
        self.assertEqual(calls, 3)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"status": "ok"})

    def test_atomic_replace_exhaustion_preserves_old_record(self):
        target = self.temp.path / "exhaustion_test.json"
        target.write_text('{"status": "original"}', encoding="utf-8")
        with mock.patch("ctxdock.storage.os.replace", side_effect=PermissionError("Locked")), mock.patch("ctxdock.storage.time.sleep"):
            with self.assertRaises(PermissionError) as ctx:
                _atomic_json(target, {"status": "new"})
            self.assertIn("Could not atomically replace", str(ctx.exception))
            self.assertIn("5 attempts", str(ctx.exception))
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"status": "original"})

    def test_extended_windows_path_is_accepted(self):
        base = self.temp.path / "records"
        base.mkdir(parents=True, exist_ok=True)
        resolved_str = str(base.resolve())
        extended_candidate = Path(f"\\\\?\\{resolved_str}\\child.json")
        result = ensure_within(base, extended_candidate)
        self.assertEqual(result.name, "child.json")

    def test_unc_path_is_normalized(self):
        unc_candidate = Path(r"\\?\UNC\server\share\records\file.json")
        normalized = _normalize_path(unc_candidate)
        self.assertTrue(normalized.startswith(r"\\server\share\records"))

    def test_sibling_prefix_is_rejected(self):
        base = self.temp.path / "records"
        base.mkdir(parents=True, exist_ok=True)
        sibling = self.temp.path / "records_sibling" / "file.json"
        sibling.parent.mkdir(parents=True, exist_ok=True)
        with self.assertRaises(SecurityError):
            ensure_within(base, sibling)

    def test_traversal_is_rejected(self):
        base = self.temp.path / "records"
        base.mkdir(parents=True, exist_ok=True)
        outside = base / ".." / "outside.json"
        with self.assertRaises(SecurityError):
            ensure_within(base, outside)


class RecordLimitsAndSecretDetectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TempHome()
        self.store = Store(self.temp.path)
        self.store.init()

    def tearDown(self):
        self.temp.cleanup()

    def test_password_patterns_recognized(self):
        patterns = [
            'password = "secretpassword"',
            '"password": "secretpassword"',
            'db_password = "secretpassword"',
            'admin_pwd: "secretpassword"',
            'password = ultrasecretvalue',
        ]
        for idx, payload in enumerate(patterns):
            with self.assertRaises(SecurityError, msg=f"Failed to reject: {payload}"):
                self.store.save({"title": f"Secret {idx}", "summary": payload}, "alpha")

    def test_exempt_redacted_placeholders(self):
        placeholders = [
            'password = "<redacted>"',
            '"password": "<redacted>"',
            'password = "[removed]"',
            '"password": "[removed]"',
            'password = "${PASSWORD}"',
            '"password": "${PASSWORD}"',
            'password = "********"',
            '"password": "********"',
            'admin_pwd: [removed]',
            'db_password = <redacted>',
        ]
        for idx, payload in enumerate(placeholders):
            rec, _ = self.store.save({"title": f"Safe {idx}", "summary": payload}, "alpha")
            self.assertTrue(rec["id"].startswith("mem-"))

    def test_continue_rejecting_other_secrets(self):
        secrets = [
            "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0\n-----END RSA PRIVATE KEY-----",
            "AKIAIOSFODNN7EXAMPLE",
            "ghp_1234567890123456789012345678901234",
            "sk-123456789012345678901234",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozG4B1ptLQ2mX_8SZkd84ee_p8cR6jE",
        ]
        for sec in secrets:
            with self.assertRaises(SecurityError):
                self.store.save({"title": "Key", "summary": f"Config uses {sec}"}, "alpha")

    def test_record_limits_exact_boundaries(self):
        exact_title = "T" * MAX_TITLE_CHARS
        exact_summary = "S" * MAX_SUMMARY_CHARS
        exact_rationale = "R" * MAX_RATIONALE_CHARS
        exact_ref = "http://example.com/" + "x" * (MAX_SOURCE_REFERENCE_CHARS - 19)
        exact_tags = [f"tag-{i:02d}-" + "t" * (MAX_TAG_CHARS - 7) for i in range(MAX_TAGS)]

        rec, _ = self.store.save({
            "title": exact_title,
            "summary": exact_summary,
            "rationale": exact_rationale,
            "tags": exact_tags,
            "source": {"reference": exact_ref},
        }, "alpha")
        self.assertTrue(rec["id"].startswith("mem-"))
        loaded = self.store.get(rec["id"])
        self.assertEqual(len(loaded["title"]), MAX_TITLE_CHARS)
        self.assertEqual(len(loaded["summary"]), MAX_SUMMARY_CHARS)

    def test_record_limits_over_limit_cases(self):
        # Title over limit
        with self.assertRaisesRegex(ValueError, "title exceeds 512 characters"):
            self.store.save({"title": "T" * (MAX_TITLE_CHARS + 1), "summary": "Valid summary"}, "alpha")

        # Summary over limit
        with self.assertRaisesRegex(ValueError, "summary exceeds 65,536 characters"):
            self.store.save({"title": "Valid title", "summary": "S" * (MAX_SUMMARY_CHARS + 1)}, "alpha")

        # Rationale over limit
        with self.assertRaisesRegex(ValueError, "rationale exceeds 65,536 characters"):
            self.store.save({"title": "Valid title", "summary": "Valid summary", "rationale": "R" * (MAX_RATIONALE_CHARS + 1)}, "alpha")

        # Source reference over limit
        with self.assertRaisesRegex(ValueError, "source.reference exceeds 4,096 characters"):
            self.store.save({"title": "Valid title", "summary": "Valid summary", "source": {"reference": "X" * (MAX_SOURCE_REFERENCE_CHARS + 1)}}, "alpha")

        # Tags count over limit
        with self.assertRaisesRegex(ValueError, "tags exceeds 64 entries"):
            self.store.save({"title": "Valid title", "summary": "Valid summary", "tags": [f"t{i}" for i in range(MAX_TAGS + 1)]}, "alpha")

        # Single tag chars over limit
        with self.assertRaisesRegex(ValueError, "A tag exceeds 128 characters"):
            self.store.save({"title": "Valid title", "summary": "Valid summary", "tags": ["T" * (MAX_TAG_CHARS + 1)]}, "alpha")

    def test_rejected_saves_create_neither_json_nor_index_rows(self):
        records_dir = self.temp.path / "records"
        initial_files = list(records_dir.rglob("*.json"))

        import sqlite3
        with sqlite3.connect(self.store.db_path) as conn:
            initial_count = conn.execute("SELECT count(*) FROM records").fetchone()[0]

        # Rejected by limit
        with self.assertRaises(ValueError):
            self.store.save({"title": "X" * 600, "summary": "Valid summary"}, "alpha")

        # Rejected by secret
        with self.assertRaises(SecurityError):
            self.store.save({"title": "Valid", "summary": 'password = "mysecretpassword"'}, "alpha")

        after_files = list(records_dir.rglob("*.json"))
        with sqlite3.connect(self.store.db_path) as conn:
            after_count = conn.execute("SELECT count(*) FROM records").fetchone()[0]

        self.assertEqual(len(after_files), len(initial_files))
        self.assertEqual(after_count, initial_count)

    def test_legacy_oversized_records_can_be_read_and_rebuilt_and_warn_in_doctor(self):
        oversized = {
            "id": "mem-legacy00000001",
            "project_id": "alpha",
            "scope": "project",
            "category": "note",
            "title": "T" * 600,
            "summary": "Legacy oversized note",
            "rationale": "",
            "tags": ["legacy"],
            "status": "active",
            "source": {"agent": "legacy", "reference": None},
            "created_at": "2026-01-01T00:00:00.000000Z",
            "updated_at": "2026-01-01T00:00:00.000000Z",
            "content_hash": "dummyhash",
            "revisions": [],
        }
        dest = self.temp.path / "records" / "alpha" / f"{oversized['id']}.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(oversized), encoding="utf-8")

        # Rebuild indexes the legacy file
        rebuilt = self.store.rebuild()
        self.assertGreaterEqual(rebuilt, 1)

        # Existing record can be read
        loaded = self.store.get(oversized["id"])
        self.assertEqual(loaded["title"], oversized["title"])

        # Doctor warns
        checks, ok = self.store.doctor(skill_dir=Path("skill/ctxdock").resolve())
        self.assertTrue(ok)
        self.assertIn("legacy_limits", checks)
        self.assertTrue(checks["legacy_limits"]["warning"])

    def test_update_enforces_limits(self):
        rec, _ = self.store.save({"title": "Original title", "summary": "Original summary"}, "alpha")
        with self.assertRaises(ValueError):
            self.store.update(rec["id"], {"title": "T" * 600})
        # Original remains unchanged
        unchanged = self.store.get(rec["id"])
        self.assertEqual(unchanged["title"], "Original title")


V1_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
CREATE TABLE IF NOT EXISTS records (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  rationale TEXT NOT NULL,
  tags TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_records_project ON records(project_id, scope, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_records_hash ON records(project_id, scope, content_hash);
CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
  id UNINDEXED, title, summary, rationale, tags, tokenize='unicode61'
);
"""


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TempHome()
        self.db_path = self.temp.path / "index.db"
        self.backups_dir = self.temp.path / "backups"
        self.records_dir = self.temp.path / "records" / "alpha"
        self.records_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp.cleanup()

    def create_v1_database(self) -> dict[str, str]:
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(V1_SCHEMA)
            record_id = "mem-v1test00000001"
            json_path = self.records_dir / f"{record_id}.json"
            record_data = {
                "id": record_id,
                "project_id": "alpha",
                "scope": "project",
                "category": "architecture",
                "title": "PostgreSQL v1 decision",
                "summary": "Use PostgreSQL for relational entities",
                "rationale": "High reliability",
                "tags": ["database"],
                "status": "active",
                "created_at": "2026-01-01T00:00:00.000000Z",
                "updated_at": "2026-01-01T00:00:00.000000Z",
                "content_hash": "hash_v1",
                "revisions": [],
            }
            json_path.write_text(json.dumps(record_data), encoding="utf-8")
            values = (
                record_id, "alpha", "project", "architecture",
                "PostgreSQL v1 decision", "Use PostgreSQL for relational entities",
                "High reliability", json.dumps(["database"]), "active",
                "2026-01-01T00:00:00.000000Z", "2026-01-01T00:00:00.000000Z",
                "hash_v1", str(json_path),
            )
            conn.execute("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
            conn.execute(
                "INSERT INTO records_fts(id, title, summary, rationale, tags) VALUES (?, ?, ?, ?, ?)",
                (record_id, "PostgreSQL v1 decision", "Use PostgreSQL for relational entities", "High reliability", "database"),
            )
        return {"id": record_id, "path": str(json_path)}

    def test_initialization_upgrades_v1_and_preserves_records(self):
        record_info = self.create_v1_database()

        # Before migration, check version
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            self.assertEqual(index.get_schema_version(conn), 1)

        # Upgrade via initialize
        index.initialize(self.db_path)

        # Verify upgraded version
        with index.connect(self.db_path) as conn:
            self.assertEqual(index.get_schema_version(conn), 2)
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(records)").fetchall()]
            self.assertIn("source", cols)

            # Existing record remains searchable
            results = index.search(conn, "PostgreSQL", "alpha")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["id"], record_info["id"])
            # source defaults safely
            self.assertEqual(results[0]["source"], {})

        # Verify a backup was created during upgrade
        backups = list(self.backups_dir.glob("index-v1-*.db"))
        self.assertTrue(len(backups) >= 1)

    def test_repeating_initialization_does_nothing(self):
        self.create_v1_database()
        index.initialize(self.db_path)
        backup_count_1 = len(list(self.backups_dir.glob("index-v1-*.db")))

        # Repeat initialization
        index.initialize(self.db_path)
        backup_count_2 = len(list(self.backups_dir.glob("index-v1-*.db")))
        self.assertEqual(backup_count_1, backup_count_2)

        with index.connect(self.db_path) as conn:
            self.assertEqual(index.get_schema_version(conn), 2)

    def test_failed_migration_leaves_backup_and_preserves_database(self):
        self.create_v1_database()

        # Induce failure during migration
        with mock.patch("ctxdock.index.set_schema_version", side_effect=RuntimeError("Disk failure")):
            with self.assertRaises(RuntimeError) as ctx:
                index.initialize(self.db_path)
            self.assertIn("Run 'ctxdock rebuild' to recover", str(ctx.exception))

        # Verify backup was left behind
        backups = list(self.backups_dir.glob("index-v1-*.db"))
        self.assertTrue(len(backups) >= 1)

        # Original database is preserved (version 1)
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            self.assertEqual(index.get_schema_version(conn), 1)

    def test_rebuild_works_after_migration(self):
        self.create_v1_database()
        store = Store(self.temp.path)
        # Initialize/migrate
        store.init()

        # Save a new record with source
        new_rec, _ = store.save({
            "title": "New decision with source",
            "summary": "Source tracking enabled",
            "source": {"agent": "codex", "reference": "PR#101"},
        }, "alpha")

        # Rebuild
        count = store.rebuild()
        self.assertGreaterEqual(count, 2)

        # Search new record and verify source is preserved
        results = store.find("tracking", "alpha", limit=5)
        self.assertEqual(results[0]["id"], new_rec["id"])
        self.assertEqual(results[0]["source"]["agent"], "codex")
        self.assertEqual(results[0]["source"]["reference"], "PR#101")


class SearchRankingAndDeduplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TempHome()
        self.store = Store(self.temp.path)
        self.store.init()

    def tearDown(self):
        self.temp.cleanup()

    def test_better_bm25_matches_never_have_lower_relevance(self):
        # Record with high keyword density in title (weight 8.0) and summary (weight 3.0)
        rec1, _ = self.store.save({
            "title": "PostgreSQL PostgreSQL deployment",
            "summary": "PostgreSQL clustering PostgreSQL deployment guide",
            "category": "architecture",
        }, "alpha")
        # Record with lower keyword presence
        rec2, _ = self.store.save({
            "title": "General database overview",
            "summary": "Mentions PostgreSQL once for reference",
            "category": "architecture",
        }, "alpha")

        results = self.store.find("PostgreSQL", "alpha", limit=5)
        self.assertGreaterEqual(len(results), 2)
        # First result is the better match
        self.assertEqual(results[0]["id"], rec1["id"])
        self.assertEqual(results[0]["relevance"], 1.0)
        self.assertEqual(results[1]["relevance"], 0.0)
        self.assertGreaterEqual(results[0]["relevance"], results[1]["relevance"])

    def test_matches_in_fields_produce_useful_snippets(self):
        # Match only in title
        self.store.save({"title": "UniqueTitleToken architecture", "summary": "No matching text here"}, "alpha")
        # Match only in summary
        self.store.save({"title": "Generic note", "summary": "Contains UniqueSummaryToken for testing"}, "alpha")
        # Match only in rationale
        self.store.save({"title": "Rationale test", "summary": "Ordinary body", "rationale": "Special UniqueRationaleToken decision"}, "alpha")
        # Match only in tags
        self.store.save({"title": "Tag test", "summary": "Ordinary text", "tags": ["UniqueTagToken"]}, "alpha")

        for token in ("UniqueTitleToken", "UniqueSummaryToken", "UniqueRationaleToken", "UniqueTagToken"):
            res = self.store.find(token, "alpha")
            self.assertEqual(len(res), 1, f"Failed to find {token}")
            self.assertTrue(res[0]["snippet"], f"Snippet empty for {token}")
            self.assertIn(token.lower(), res[0]["snippet"].lower(), f"Snippet missing token {token}")

    def test_near_duplicates_deduplication_preserves_requested_limit(self):
        # 5 near-duplicates that share ~98% text
        base_text = "Standardization decision for component pipelines in cloud native enterprise environments."
        for i in range(5):
            self.store.save({
                "title": f"Pipeline Standard {i}",
                "summary": f"{base_text} Variant marker {i}.",
                "category": "architecture",
            }, "alpha")

        # 5 distinct records also matching "standardization"
        distinct_topics = [
            ("Database Engine", "PostgreSQL was selected for transactional ACID guarantees and relational modeling."),
            ("Cache Infrastructure", "Redis in-memory caching stores ephemeral session state with five minute TTLs."),
            ("Message Broker", "Apache Kafka streams event messages between distributed background workers."),
            ("Authentication Gateway", "OAuth2 authorization server issues short-lived JWT bearer tokens."),
            ("Metrics Telemetry", "Prometheus scrapes OpenTelemetry metrics endpoints on internal port 9090."),
        ]
        for title, summary in distinct_topics:
            self.store.save({
                "title": title,
                "summary": f"{summary} Adheres to engineering standardization guideline.",
                "category": "architecture",
            }, "alpha")

        # Request limit=5. Even though the first 5 are near-duplicates and 4 get deduplicated,
        # the expanded candidate limit (min(max(5*4, 5), 400) = 20) ensures 5 total results are returned.
        results = self.store.find("standardization", "alpha", limit=5)
        self.assertEqual(len(results), 5)

    def test_active_records_remain_ahead_of_superseded_records(self):
        # Old record has many repetitions of search terms
        old_rec, _ = self.store.save({
            "title": "Auth token auth token auth token",
            "summary": "auth token auth token auth token auth token auth token",
            "category": "security",
        }, "alpha")
        # Mark it superseded by a new active record
        new_rec, _ = self.store.save({
            "title": "Auth decision",
            "summary": "Use auth token with JWT",
            "supersedes": old_rec["id"],
            "category": "security",
        }, "alpha")

        results = self.store.find("auth token", "alpha", limit=5)
        self.assertEqual(results[0]["id"], new_rec["id"])
        self.assertEqual(results[0]["status"], "active")
        self.assertEqual(results[1]["id"], old_rec["id"])
        self.assertEqual(results[1]["status"], "superseded")


if __name__ == "__main__":
    unittest.main()

