"""Command-line interface for CNetPD-Skill-Builder."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from . import VERSION
from .builder import build
from .constants import PROJECT_NAME, SKILL_NAME


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def main(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    default_output_root = repo_root / ".output"
    default_dist_root = repo_root / "dist"
    default_target = default_dist_root / SKILL_NAME
    parser = argparse.ArgumentParser(
        description=f"{PROJECT_NAME} - build {SKILL_NAME}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 tools/build_cnetpd_skill.py
  python3 tools/build_cnetpd_skill.py --refresh-meta
  python3 tools/build_cnetpd_skill.py --no-prepare --source-dir .output/splitter
        """,
    )
    parser.add_argument("--source-dir", type=Path, default=default_output_root / "splitter")
    parser.add_argument("--api-meta-dir", type=Path, default=default_output_root / "api_metadata")
    parser.add_argument("--target", "-t", type=Path, default=default_target)
    parser.add_argument("--no-prepare", action="store_true")
    parser.add_argument("--refresh-meta", action="store_true")
    parser.add_argument("--force", "-f", action="store_true")
    parser.add_argument("--no-overwrite", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    t0 = time.time()
    force = args.force or (args.target == default_target and not args.no_overwrite)
    result = build(
        api_meta_dir=args.api_meta_dir,
        output_dir=args.source_dir,
        target_dir=args.target,
        package_dir=Path(__file__).resolve().parent,
        no_prepare=args.no_prepare,
        refresh_meta=args.refresh_meta,
        force=force,
    )
    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print(f"  {SKILL_NAME} build complete ({elapsed:.1f}s)")
    print("=" * 60)
    print(f"  output: {result['target']}")
    print(f"  zip: {result['zip']}")
    print(f"  skill: {result['skill']}")
    print(f"  products: {result['products_copied']}")
    print(f"  L-1 index: {result['index_bytes'] / 1024:.1f} KB")
    print(f"  manifest: {result['manifest_bytes'] / 1024:.1f} KB")
    print(f"  topics: {result['topics_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
