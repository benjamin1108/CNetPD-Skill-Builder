"""Data manifest generation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .constants import DATA_SCHEMA_VERSION, PRODUCT_CODES, PROVIDER


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def build_manifest(data_dir: Path, *, kind: str) -> dict:
    checksums = {}
    for path in sorted(data_dir.rglob("*.json")):
        if path.name == "_manifest.json":
            continue
        checksums[path.relative_to(data_dir).as_posix()] = sha256(path)

    product_stats = []
    provider_dir = data_dir / "providers" / PROVIDER
    for product in PRODUCT_CODES:
        index_file = provider_dir / product / "index.json"
        if not index_file.exists():
            continue
        index = json.loads(index_file.read_text(encoding="utf-8"))
        product_stats.append({
            "provider": PROVIDER,
            "product": product,
            "apiCount": index.get("totalApis", 0),
            "groupCount": len(index.get("groups", [])),
        })

    return {
        "schema_version": DATA_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "aliyun-api-meta",
        "kind": kind,
        "providers": [PROVIDER],
        "products": PRODUCT_CODES,
        "product_stats": product_stats,
        "file_count": len(checksums),
        "checksums": checksums,
    }


def write_manifest(data_dir: Path, *, kind: str) -> Path:
    path = data_dir / "_manifest.json"
    path.write_text(
        json.dumps(build_manifest(data_dir, kind=kind), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
