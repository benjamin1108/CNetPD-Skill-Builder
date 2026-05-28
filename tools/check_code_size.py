#!/usr/bin/env python3
"""Fail when a Python source file exceeds the CNetPD 500-line gate."""

from __future__ import annotations

import sys
from pathlib import Path

MAX_LINES = 500
EXCLUDED_DIRS = {
    ".git",
    ".output",
    ".venv",
    "__pycache__",
    "dist",
    "tmp",
}


def should_skip(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts)


def line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    offenders = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if should_skip(rel):
            continue
        count = line_count(path)
        if count > MAX_LINES:
            offenders.append((rel, count))
    if offenders:
        print(f"Code size gate failed: Python files must be <= {MAX_LINES} lines.", file=sys.stderr)
        for rel, count in offenders:
            print(f"  {rel}: {count}", file=sys.stderr)
        return 1
    print(f"Code size gate passed: all Python files <= {MAX_LINES} lines.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
