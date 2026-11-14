from __future__ import annotations

import filecmp
import io
import json
import os
import sqlite3
import subprocess
import sys
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock
import unittest

from ctxdock.cli import main
from ctxdock.installer import install, uninstall
from tests.helpers import TempHome


class CliInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TempHome()

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, arguments, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"CTXDOCK_HOME": str(self.temp.path)}), mock.patch("sys.stdin", io.StringIO(stdin)), redirect_stdout(out), redirect_stderr(err):
            code = main(arguments)
        return code, out.getvalue(), err.getvalue()

    def test_cli_init_save_find_get_list_update_and_exit_codes(self):
        self.assertEqual(self.invoke(["init"])[0], 0)
        payload = json.dumps({"title": "API decision", "summary": "Use REST for the public API", "category": "architecture"})
        code, output, _ = self.invoke(["save", "--project", "cli"], payload)
        self.assertEqual(code, 0)
        record = json.loads(output)["record"]
        code, output, _ = self.invoke(["find", "REST", "--project", "cli"])
        self.assertEqual(json.loads(output)[0]["id"], record["id"])
        self.assertEqual(self.invoke(["get", record["id"]])[0], 0)
        self.assertEqual(self.invoke(["list", "--project", "cli"])[0], 0)
        changes = json.dumps({"summary": "Use REST v2", "expected_updated_at": record["updated_at"]})
        self.assertEqual(self.invoke(["update", record["id"]], changes)[0], 0)
        self.assertEqual(self.invoke(["get", "mem-missing"])[0], 2)

    def test_cli_malformed_json_and_query(self):
        self.invoke(["init"])
        self.assertEqual(self.invoke(["save", "--project", "cli"], "{")[0], 2)
        self.assertEqual(self.invoke(["find", "+++", "--project", "cli"])[0], 2)

    def test_help_for_every_command(self):
        for command in ("init", "save", "find", "get", "list", "update", "handoff", "rebuild", "doctor", "stats", "install-skill", "uninstall-skill"):
            with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
                main([command, "--help"])
            self.assertEqual(raised.exception.code, 0)

    def test_install_reinstall_and_uninstall_preserve_memory(self):
        target = self.temp.path / "skills" / "ctxdock"
        memory = self.temp.path / "memory-marker.json"
        memory.write_text("{}", encoding="utf-8")
        install(target)
        self.assertTrue((target / "SKILL.md").is_file())
        with self.assertRaises(FileExistsError):
            install(target)
        install(target, upgrade=True)
        uninstall(target)
        self.assertFalse(target.exists())
        self.assertTrue(memory.exists())

    def test_uninstall_refuses_unrelated_directory(self):
        target = self.temp.path / "ctxdock"
        target.mkdir()
        (target / "important.txt").write_text("keep", encoding="utf-8")
        with self.assertRaises(ValueError):
            uninstall(target)
        self.assertTrue((target / "important.txt").exists())

    def test_doctor_reports_missing_skill_with_nonzero_exit(self):
        self.invoke(["init"])
        code, output, _ = self.invoke(["doctor", "--skill-dir", str(self.temp.path / "missing")])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(output)["skill"]["ok"])

    def test_sqlite_errors_return_cli_exit_code_2(self):
        self.invoke(["init"])
        with mock.patch("ctxdock.storage.index.search", side_effect=sqlite3.OperationalError("database is locked")):
            code, out, err = self.invoke(["find", "test"])
            self.assertEqual(code, 2)
            self.assertIn("ctxdock: error: database is locked", err)
            self.assertNotIn("Traceback", err)

    def test_skill_installation_from_source_and_wheel_matches_byte_for_byte(self):
        root = Path(__file__).resolve().parents[1]
        canonical_dir = root / "skill" / "ctxdock"

        # 1. Install from current source checkout
        target_source = self.temp.path / "skills_source" / "ctxdock"
        install(target_source)
        self.assertTrue((target_source / "SKILL.md").is_file())

        # 2. Build a wheel in a temp directory
        wheel_dir = self.temp.path / "wheels"
        wheel_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", str(wheel_dir), str(root)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, f"pip wheel failed: {proc.stderr}")
        wheels = list(wheel_dir.glob("*.whl"))
        self.assertEqual(len(wheels), 1)

        # 3. Extract skill from wheel
        target_wheel = self.temp.path / "skills_wheel" / "ctxdock"
        target_wheel.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(wheels[0]) as z:
            for member in z.namelist():
                if member.startswith("ctxdock/_skill/"):
                    rel = member[len("ctxdock/_skill/"):]
                    if rel:
                        dest = target_wheel / rel
                        if member.endswith("/"):
                            dest.mkdir(parents=True, exist_ok=True)
                        else:
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            dest.write_bytes(z.read(member))

        # 4. Compare installed skill files from source, wheel, and canonical byte-for-byte
        source_files = {
            p.relative_to(target_source)
            for p in target_source.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith(".pyc")
        }
        wheel_files = {
            p.relative_to(target_wheel)
            for p in target_wheel.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith(".pyc")
        }
        canonical_files = {
            p.relative_to(canonical_dir)
            for p in canonical_dir.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith(".pyc")
        }

        self.assertEqual(source_files, wheel_files)
        self.assertEqual(source_files, canonical_files)

        for rel in sorted(source_files):
            src_file = target_source / rel
            whl_file = target_wheel / rel
            canon_file = canonical_dir / rel
            self.assertTrue(filecmp.cmp(src_file, whl_file, shallow=False), f"Drift between source and wheel in {rel}")
            self.assertTrue(filecmp.cmp(src_file, canon_file, shallow=False), f"Drift between source and canonical in {rel}")


if __name__ == "__main__":
    unittest.main()
