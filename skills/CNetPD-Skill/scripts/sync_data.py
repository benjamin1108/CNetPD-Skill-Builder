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
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import aliyun_splitter  # noqa: E402
import aws_splitter  # noqa: E402
from indexing import build_cnetpd_index  # noqa: E402
from cnetpd_constants import (  # noqa: E402
    ALIYUN_PROVIDER,
    AWS_API_MODELS_CONTENTS_URL,
    AWS_API_MODELS_RAW_URL,
    AWS_MODEL_VERSIONS,
    AWS_PRODUCTS,
    AWS_PROVIDER,
    BASE_URL,
    DATA_SCHEMA_VERSION,
    DEFAULT_CACHE_DIR,
    PRODUCT_CODES,
    PRODUCT_CODES_BY_PROVIDER,
    PRODUCTS_URL,
    SKILL_VERSION,
)


def log(message: str, *, quiet: bool) -> None:
    if not quiet:
        print(message, file=sys.stderr)


def fetch_json(url: str, *, timeout: int = 90) -> dict | list:
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


def download_aliyun_metadata(api_meta_dir: Path, *, quiet: bool) -> None:
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
        log(f"download aliyun metadata: {product}", quiet=quiet)
        url = f"{BASE_URL}products/{code}/versions/{version}/api-docs.json"
        (api_meta_dir / f"{code}.json").write_text(
            json.dumps(fetch_api_docs(url, product), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def github_contents(path: str) -> list[dict]:
    url = f"{AWS_API_MODELS_CONTENTS_URL}/{urllib.parse.quote(path.strip('/'))}"
    data = fetch_json(url)
    if not isinstance(data, list):
        raise RuntimeError(f"GitHub contents response is not a list: {path}")
    return [item for item in data if isinstance(item, dict)]


def aws_source_services() -> list[str]:
    return sorted({item.get("sourceService", item["product"]) for item in AWS_PRODUCTS})


def latest_aws_model(source_service: str) -> tuple[str, str, str]:
    if source_service in AWS_MODEL_VERSIONS:
        version = AWS_MODEL_VERSIONS[source_service]
        name = f"{source_service}-{version}.json"
        return version, name, f"{AWS_API_MODELS_RAW_URL}/{source_service}/service/{version}/{name}"
    versions = sorted(
        item["name"]
        for item in github_contents(f"{source_service}/service")
        if item.get("type") == "dir" and item.get("name")
    )
    if not versions:
        raise RuntimeError(f"AWS service has no versions: {source_service}")
    version = versions[-1]
    files = github_contents(f"{source_service}/service/{version}")
    model = next((item for item in files if str(item.get("name", "")).endswith(".json")), None)
    if not model:
        raise RuntimeError(f"AWS service version has no JSON model: {source_service}/{version}")
    name = str(model["name"])
    download_url = model.get("download_url") or f"{AWS_API_MODELS_RAW_URL}/{source_service}/service/{version}/{name}"
    return version, name, str(download_url)


def download_aws_metadata(api_meta_dir: Path, *, quiet: bool) -> None:
    api_meta_dir.mkdir(parents=True, exist_ok=True)
    for service in aws_source_services():
        log(f"download aws model: {service}", quiet=quiet)
        version, name, url = latest_aws_model(service)
        data = fetch_json(url)
        if not isinstance(data, dict) or not data.get("shapes"):
            raise RuntimeError(f"AWS model is invalid; missing shapes: {service}")
        out = api_meta_dir / service / "service" / version / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def product_stats(data_dir: Path) -> list[dict]:
    stats = []
    for provider, products in PRODUCT_CODES_BY_PROVIDER.items():
        provider_dir = data_dir / "providers" / provider
        for product in products:
            index_file = provider_dir / product / "index.json"
            if not index_file.exists():
                continue
            idx = json.loads(index_file.read_text(encoding="utf-8"))
            stats.append({
                "provider": provider,
                "product": product,
                "sourceService": idx.get("sourceService", product),
                "apiCount": idx.get("totalApis", 0),
                "sourceApiCount": idx.get("sourceOperationCount"),
                "groupCount": len(idx.get("groups", [])),
            })
    return stats


def write_manifest(data_dir: Path) -> None:
    checksums = {}
    for path in sorted(data_dir.rglob("*.json")):
        if path.name == "_manifest.json":
            continue
        checksums[path.relative_to(data_dir).as_posix()] = sha256(path)
    providers = list(PRODUCT_CODES_BY_PROVIDER)
    manifest = {
        "schema_version": DATA_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "cloud-api-meta",
        "kind": "cache",
        "providers": providers,
        "products": [
            {"provider": provider, "product": product}
            for provider, products in PRODUCT_CODES_BY_PROVIDER.items()
            for product in products
        ],
        "product_stats": product_stats(data_dir),
        "file_count": len(checksums),
        "checksums": checksums,
    }
    (data_dir / "_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def split_metadata(api_meta_dir: Path, output_dir: Path, *, quiet: bool) -> None:
    log("split aliyun metadata", quiet=quiet)
    aliyun_output = output_dir / "providers" / ALIYUN_PROVIDER
    aliyun_result = aliyun_splitter.split_batch(api_meta_dir / ALIYUN_PROVIDER, aliyun_output, products_filter=set(PRODUCT_CODES), validate=True)
    log("split aws metadata", quiet=quiet)
    aws_output = output_dir / "providers" / AWS_PROVIDER
    aws_result = aws_splitter.split_batch(api_meta_dir / AWS_PROVIDER, aws_output, products=AWS_PRODUCTS, validate=True)
    errors = [*aliyun_result.get("errors", []), *aws_result.get("errors", [])]
    if errors:
        raise RuntimeError(f"splitter validation failed: {errors[:5]}")


def build_data(staging: Path, *, quiet: bool) -> Path:
    api_meta_dir = staging / "api_metadata"
    output_dir = staging / "output"
    data_dir = staging / "data"
    download_aliyun_metadata(api_meta_dir / ALIYUN_PROVIDER, quiet=quiet)
    download_aws_metadata(api_meta_dir / AWS_PROVIDER, quiet=quiet)
    split_metadata(api_meta_dir, output_dir, quiet=quiet)
    providers_dir = data_dir / "providers"
    providers_dir.mkdir(parents=True)
    for provider in PRODUCT_CODES_BY_PROVIDER:
        shutil.copytree(output_dir / "providers" / provider, providers_dir / provider)
    (data_dir / "_cnetpd-index.json").write_text(
        json.dumps(build_cnetpd_index(data_dir), ensure_ascii=False, indent=2),
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
