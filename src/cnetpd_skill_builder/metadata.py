"""Download Aliyun API metadata used by the current CNetPD provider."""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

from .constants import BASE_URL, PRODUCT_CODES, PRODUCTS_URL


def fetch_json(url: str, *, timeout: int = 60) -> dict | list:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "CNetPD-Skill-Builder/1.0"},
    )
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


def find_api_meta(api_meta_dir: Path, product: str) -> Path | None:
    direct = api_meta_dir / f"{product}.json"
    if direct.exists():
        return direct
    matches = sorted(api_meta_dir.rglob(f"{product}.json"))
    return matches[0] if matches else None


def missing_metadata(api_meta_dir: Path) -> list[str]:
    return [product for product in PRODUCT_CODES if find_api_meta(api_meta_dir, product) is None]


def sanitize_dir_name(value: str) -> str:
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in value)


def download_network_metadata(api_meta_dir: Path, *, refresh: bool = False) -> list[str]:
    """Download only the Aliyun networking products needed by CNetPD."""
    api_meta_dir.mkdir(parents=True, exist_ok=True)
    missing = missing_metadata(api_meta_dir)
    if not refresh and not missing:
        return []

    products_data = fetch_json(PRODUCTS_URL)
    if not isinstance(products_data, list):
        raise RuntimeError("products.json response is not a list")

    by_code = {
        str(item.get("code", "")).lower(): item
        for item in products_data
        if isinstance(item, dict)
    }
    downloaded: list[str] = []
    for product in (PRODUCT_CODES if refresh else missing):
        meta = by_code.get(product.lower())
        if not meta:
            raise RuntimeError(f"Aliyun product not found: {product}")

        code = meta.get("code") or product
        versions = meta.get("versions", [])
        version = meta.get("defaultVersion") or (versions[0] if versions else None)
        if not version:
            raise RuntimeError(f"{product} has no downloadable version")

        category2 = sanitize_dir_name(meta.get("category2Name", "Uncategorized"))
        category = sanitize_dir_name(meta.get("categoryName", "Uncategorized"))
        out_dir = api_meta_dir / category2 / category
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{code}.json"
        if out_file.exists() and not refresh:
            continue

        url = f"{BASE_URL}products/{code}/versions/{version}/api-docs.json"
        out_file.write_text(
            json.dumps(fetch_api_docs(url, product), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        downloaded.append(product)
    return downloaded
