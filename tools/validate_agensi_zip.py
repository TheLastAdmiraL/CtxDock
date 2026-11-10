#!/usr/bin/env python3
"""Validator for Agensi package ZIP compliance.

Confirms:
1. Exactly one SKILL.md
2. Valid UTF-8 and YAML frontmatter
3. No .git, databases, caches, credentials, virtual environments, or binaries
4. No absolute paths or .. ZIP entries
5. Total size below 50 MB
6. Standalone script launches successfully
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

FORBIDDEN_EXTENSIONS = {
    ".db", ".sqlite", ".sqlite3", ".pyc", ".pyo", ".pyd",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".env", ".pem", ".key",
}

FORBIDDEN_NAMES = {
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    ".DS_Store", "credentials", "credentials.json",
}


def validate_zip(zip_path: Path) -> bool:
    if not zip_path.is_file():
        print(f"Error: ZIP file does not exist: {zip_path}", file=sys.stderr)
        return False

    size = zip_path.stat().st_size
    max_size = 50 * 1024 * 1024
    if size > max_size:
        print(f"Error: ZIP size {size:,} bytes exceeds 50 MB limit.", file=sys.stderr)
        return False

    with zipfile.ZipFile(zip_path, "r") as z:
        names = z.namelist()
        skill_files = []

        for name in names:
            # Check for absolute paths
            if name.startswith("/") or name.startswith("\\") or (len(name) > 1 and name[1] == ":"):
                print(f"Error: Absolute path found in ZIP: {name}", file=sys.stderr)
                return False

            # Check for path traversal
            parts = Path(name).parts
            if ".." in parts:
                print(f"Error: Directory traversal entry found in ZIP: {name}", file=sys.stderr)
                return False

            # Check for forbidden directories/files
            for part in parts:
                if part in FORBIDDEN_NAMES:
                    print(f"Error: Forbidden directory/file name in ZIP: {name}", file=sys.stderr)
                    return False

            # Check for forbidden extensions
            ext = Path(name).suffix.lower()
            if ext in FORBIDDEN_EXTENSIONS:
                print(f"Error: Forbidden file extension '{ext}' in ZIP: {name}", file=sys.stderr)
                return False

            if Path(name).name == "SKILL.md":
                skill_files.append(name)

        if len(skill_files) != 1:
            print(f"Error: Expected exactly one SKILL.md, found {len(skill_files)}: {skill_files}", file=sys.stderr)
            return False

        skill_name = skill_files[0]
        try:
            content = z.read(skill_name).decode("utf-8")
        except UnicodeDecodeError as exc:
            print(f"Error: {skill_name} is not valid UTF-8: {exc}", file=sys.stderr)
            return False

        if not content.startswith("---"):
            print("Error: SKILL.md does not start with YAML frontmatter delimiter (---).", file=sys.stderr)
            return False

        parts = content.split("---", 2)
        if len(parts) < 3:
            print("Error: SKILL.md does not have closed YAML frontmatter (---).", file=sys.stderr)
            return False

        frontmatter = parts[1]
        if "name:" not in frontmatter or "description:" not in frontmatter:
            print("Error: SKILL.md frontmatter missing 'name:' or 'description:'.", file=sys.stderr)
            return False

    # Test standalone script in temporary extraction
    with tempfile.TemporaryDirectory(prefix="agensi-val-") as tmpdir:
        tmp_path = Path(tmpdir)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmp_path)

        script_path = tmp_path / "scripts" / "ctxdock.py"
        if not script_path.is_file():
            print("Error: scripts/ctxdock.py missing from extracted ZIP.", file=sys.stderr)
            return False

        # Test execution
        proc = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(f"Error: Standalone script failed --help: {proc.stderr}", file=sys.stderr)
            return False

        # Test isolated CTXDOCK_HOME operations
        smoke_home = tmp_path / ".smoke-home"
        import os
        env = {**os.environ, "CTXDOCK_HOME": str(smoke_home)}

        # Init
        p_init = subprocess.run([sys.executable, str(script_path), "init"], capture_output=True, text=True, env=env)
        if p_init.returncode != 0:
            print(f"Error: Standalone script failed 'init': {p_init.stderr}", file=sys.stderr)
            return False

        # Save
        p_save = subprocess.run(
            [sys.executable, str(script_path), "save", "--project", "val-alpha"],
            input='{"title": "Agensi Validation", "summary": "Standalone script functions correctly."}',
            capture_output=True,
            text=True,
            env=env,
        )
        if p_save.returncode != 0:
            print(f"Error: Standalone script failed 'save': {p_save.stderr}", file=sys.stderr)
            return False

        # Find in alpha
        p_find_alpha = subprocess.run(
            [sys.executable, str(script_path), "find", "Validation", "--project", "val-alpha"],
            capture_output=True,
            text=True,
            env=env,
        )
        if p_find_alpha.returncode != 0 or "Agensi Validation" not in p_find_alpha.stdout:
            print(f"Error: Standalone script failed 'find' in project alpha: {p_find_alpha.stderr}", file=sys.stderr)
            return False

        # Find in beta (must not find)
        p_find_beta = subprocess.run(
            [sys.executable, str(script_path), "find", "Validation", "--project", "val-beta"],
            capture_output=True,
            text=True,
            env=env,
        )
        if p_find_beta.returncode != 0 or "Agensi Validation" in p_find_beta.stdout:
            print("Error: Standalone script leaked record across projects!", file=sys.stderr)
            return False

    print(f"Agensi package validation PASSED for {zip_path.name}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Agensi ZIP package.")
    parser.add_argument("zip_path", type=Path, help="Path to Agensi ZIP archive")
    args = parser.parse_args()

    return 0 if validate_zip(args.zip_path) else 1


if __name__ == "__main__":
    raise SystemExit(main())
