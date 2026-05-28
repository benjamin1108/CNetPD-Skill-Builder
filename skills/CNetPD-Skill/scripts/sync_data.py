#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Refresh CNetPD-Skill runtime data cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import aliyun_splitter  # noqa: E402
from cnetpd_constants import (  # noqa: E402
    BASE_URL,
    DATA_SCHEMA_VERSION,
    DEFAULT_CACHE_DIR,
    PRODUCT_CODES,
    PRODUCTS,
    PRODUCTS_URL,
    PROJECT_DESCRIPTION,
    PROJECT_NAME,
    PROVIDER,
    PROVIDER_DISPLAY,
    SKILL_NAME,
    SKILL_VERSION,
    TOPICS,
)


def log(message: str, *, quiet: bool) -> None:
    if not quiet:
        print(message, file=sys.stderr)


def fetch_json(url: str, *, timeout: int = 60) -> dict | list:
    request = urllib.request.Request(url, headers={"User-Agent": "CNetPD-Skill/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_api_docs(url: str, product: str, *, retries: int = 3) -> dict:
    last_shape = ""
    for attempt in range(1, retries + 1):
        data = fetch_json(url)
        if isinstance(data, dict) and data.get("apis"):
            return data
        last_shape = ", ".join(data.keys()) if isinstance(data, dict) else type(data).__name__
        if attempt < retries:
            time.sleep(1)
    raise RuntimeError(f"{product} metadata is invalid; missing apis: {last_shape}")


def download_metadata(api_meta_dir: Path, *, quiet: bool) -> None:
    api_meta_dir.mkdir(parents=True, exist_ok=True)
    products_data = fetch_json(PRODUCTS_URL)
    if not isinstance(products_data, list):
        raise RuntimeError("products.json response is not a list")
    by_code = {
        str(item.get("code", "")).lower(): item
        for item in products_data
        if isinstance(item, dict)
    }
    for product in PRODUCT_CODES:
        meta = by_code.get(product.lower())
        if not meta:
            raise RuntimeError(f"Aliyun product not found: {product}")
        code = meta.get("code") or product
        versions = meta.get("versions", [])
        version = meta.get("defaultVersion") or (versions[0] if versions else None)
        if not version:
            raise RuntimeError(f"{product} has no downloadable version")
        log(f"download metadata: {product}", quiet=quiet)
        url = f"{BASE_URL}products/{code}/versions/{version}/api-docs.json"
        (api_meta_dir / f"{code}.json").write_text(
            json.dumps(fetch_api_docs(url, product), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def expand_topic_apis(topic: dict, provider_dir: Path) -> dict:
    keywords = [keyword.lower() for keyword in topic.get("keywords", [])]
    result = {}
    for ref in topic.get("products", []):
        product = ref["product"]
        groups_dir = provider_dir / product / "groups"
        if not groups_dir.exists():
            continue
        hits = []
        for group_file in sorted(groups_dir.glob("*.json")):
            group = json.loads(group_file.read_text(encoding="utf-8"))
            for api in group.get("apis", []):
                haystack = f"{api.get('name', '')} {api.get('summary', '')}".lower()
                if any(keyword in haystack for keyword in keywords):
                    hits.append({
                        "api": api.get("name", ""),
                        "group": group.get("group", group_file.stem),
                        "summary": api.get("summary", ""),
                    })
                    if len(hits) >= 8:
                        break
            if len(hits) >= 8:
                break
        if hits:
            result[f"{PROVIDER}/{product}"] = hits
    return result


def build_index(data_dir: Path) -> dict:
    provider_dir = data_dir / "providers" / PROVIDER
    products = []
    for meta in PRODUCTS:
        index_file = provider_dir / meta["product"] / "index.json"
        product_index = json.loads(index_file.read_text(encoding="utf-8"))
        products.append({
            "provider": PROVIDER,
            "product": meta["product"],
            "slug": meta["product"].lower(),
            "display": meta["display"],
            "summary": meta["summary"],
            "coverage": meta["coverage"],
            "apiCount": product_index.get("totalApis", 0),
            "groupCount": len(product_index.get("groups", [])),
        })
    topics = []
    for topic in TOPICS:
        item = {
            "slug": topic["slug"],
            "title": topic["title"],
            "description": topic["description"],
            "products": topic["products"],
            "decisions": [{"when": when, "use": use} for when, use in topic["decisions"]],
        }
        relevant = expand_topic_apis(topic, provider_dir)
        if relevant:
            item["relevantApis"] = relevant
        topics.append(item)
    return {
        "_layer": "L-1",
        "_version": SKILL_VERSION,
        "skill": SKILL_NAME,
        "project": PROJECT_NAME,
        "domain": "cloud-networking",
        "description": PROJECT_DESCRIPTION,
        "providers": [{"slug": PROVIDER, "display": PROVIDER_DISPLAY, "productCount": len(products)}],
        "productCount": len(products),
        "topicCount": len(topics),
        "products": products,
        "topics": topics,
    }


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def write_manifest(data_dir: Path) -> None:
    checksums = {}
    for path in sorted(data_dir.rglob("*.json")):
        if path.name == "_manifest.json":
            continue
        checksums[path.relative_to(data_dir).as_posix()] = sha256(path)
    product_stats = []
    provider_dir = data_dir / "providers" / PROVIDER
    for product in PRODUCT_CODES:
        idx = json.loads((provider_dir / product / "index.json").read_text(encoding="utf-8"))
        product_stats.append({
            "provider": PROVIDER,
            "product": product,
            "apiCount": idx.get("totalApis", 0),
            "groupCount": len(idx.get("groups", [])),
        })
    manifest = {
        "schema_version": DATA_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "aliyun-api-meta",
        "kind": "cache",
        "providers": [PROVIDER],
        "products": PRODUCT_CODES,
        "product_stats": product_stats,
        "file_count": len(checksums),
        "checksums": checksums,
    }
    (data_dir / "_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def build_data(staging: Path, *, quiet: bool) -> Path:
    api_meta_dir = staging / "api_metadata"
    output_dir = staging / "output"
    data_dir = staging / "data"
    provider_dir = data_dir / "providers" / PROVIDER
    download_metadata(api_meta_dir, quiet=quiet)
    log("split metadata", quiet=quiet)
    result = aliyun_splitter.split_batch(api_meta_dir, output_dir, products_filter=set(PRODUCT_CODES), validate=True)
    if result.get("errors"):
        raise RuntimeError(f"splitter validation failed: {result['errors'][:5]}")
    provider_dir.mkdir(parents=True)
    for product in PRODUCT_CODES:
        shutil.copytree(output_dir / product, provider_dir / product)
    (data_dir / "_cnetpd-index.json").write_text(
        json.dumps(build_index(data_dir), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_manifest(data_dir)
    return data_dir


def replace_target(staged_data: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = target.with_name(target.name + ".bak")
    if backup.exists():
        shutil.rmtree(backup)
    moved_old = False
    if target.exists():
        target.rename(backup)
        moved_old = True
    try:
        shutil.move(str(staged_data), str(target))
    except Exception:
        if moved_old and backup.exists() and not target.exists():
            backup.rename(target)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync CNetPD-Skill data")
    parser.add_argument("--target", type=Path, default=Path(DEFAULT_CACHE_DIR).expanduser())
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    target = args.target.expanduser()
    staging = target.parent / f".sync-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        replace_target(build_data(staging, quiet=args.quiet), target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    log(f"sync complete: {target}", quiet=args.quiet)


if __name__ == "__main__":
    main()
