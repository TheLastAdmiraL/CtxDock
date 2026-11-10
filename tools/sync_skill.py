#!/usr/bin/env python3
"""Synchronize canonical skill definition into the packaged _skill directory."""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "skill" / "ctxdock"
PACKAGED = ROOT / "src" / "ctxdock" / "_skill"


def get_relative_files(directory: Path) -> set[Path]:
    if not directory.exists():
        return set()
    return {
        path.relative_to(directory)
        for path in directory.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and not path.name.endswith(".pyc")
    }


def check_sync() -> bool:
    canonical_files = get_relative_files(CANONICAL)
    packaged_files = get_relative_files(PACKAGED)

    if canonical_files != packaged_files:
        missing_in_pkg = canonical_files - packaged_files
        extra_in_pkg = packaged_files - canonical_files
        if missing_in_pkg:
            print(f"Error: Missing in packaged skill: {[str(p) for p in sorted(missing_in_pkg)]}", file=sys.stderr)
        if extra_in_pkg:
            print(f"Error: Extra files in packaged skill: {[str(p) for p in sorted(extra_in_pkg)]}", file=sys.stderr)
        return False

    for rel in sorted(canonical_files):
        src = CANONICAL / rel
        dst = PACKAGED / rel
        if not filecmp.cmp(src, dst, shallow=False):
            print(f"Error: Byte-for-byte mismatch in {rel}", file=sys.stderr)
            return False

    print("Canonical and packaged skill definitions match byte-for-byte.")
    return True


def sync() -> None:
    PACKAGED.mkdir(parents=True, exist_ok=True)

    # Remove extra files in packaged
    canonical_files = get_relative_files(CANONICAL)
    packaged_files = get_relative_files(PACKAGED)
    for extra in packaged_files - canonical_files:
        (PACKAGED / extra).unlink(missing_ok=True)

    for rel in sorted(canonical_files):
        src = CANONICAL / rel
        dst = PACKAGED / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    print(f"Synchronized {len(canonical_files)} skill file(s) from {CANONICAL} to {PACKAGED}.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize or verify canonical CtxDock skill files.")
    parser.add_argument("--check", action="store_true", help="Verify that packaged files match canonical files exactly.")
    args = parser.parse_args()

    if args.check:
        return 0 if check_sync() else 1
    sync()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
