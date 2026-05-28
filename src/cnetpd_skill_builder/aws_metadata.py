"""Download or copy AWS Smithy API models used by CNetPD."""

from __future__ import annotations

import json
import shutil
import urllib.parse
from pathlib import Path

from .aws_splitter import find_model
from .constants import AWS_API_MODELS_CONTENTS_URL, AWS_API_MODELS_RAW_URL, AWS_MODEL_VERSIONS, AWS_PRODUCTS
from .metadata import fetch_json


def source_services() -> list[str]:
    return sorted({item.get("sourceService", item["product"]) for item in AWS_PRODUCTS})


def metadata_model_path(api_meta_dir: Path, source_service: str) -> Path | None:
    return find_model(api_meta_dir, source_service)


def missing_aws_metadata(api_meta_dir: Path) -> list[str]:
    return [service for service in source_services() if metadata_model_path(api_meta_dir, service) is None]


def copy_model(source_model: Path, api_meta_dir: Path, source_service: str) -> Path:
    version = source_model.parent.name
    out = api_meta_dir / source_service / "service" / version / source_model.name
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_model, out)
    return out


def copy_aws_metadata(api_meta_dir: Path, models_dir: Path, *, refresh: bool = False) -> list[str]:
    copied = []
    for service in source_services():
        if not refresh and metadata_model_path(api_meta_dir, service) is not None:
            continue
        source_model = find_model(models_dir, service)
        if source_model is None:
            continue
        copy_model(source_model, api_meta_dir, service)
        copied.append(service)
    return copied


def github_contents(path: str) -> list[dict]:
    url = f"{AWS_API_MODELS_CONTENTS_URL}/{urllib.parse.quote(path.strip('/'))}"
    data = fetch_json(url)
    if not isinstance(data, list):
        raise RuntimeError(f"GitHub contents response is not a list: {path}")
    return [item for item in data if isinstance(item, dict)]


def latest_model_download(source_service: str) -> tuple[str, str, str]:
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


def download_aws_metadata(api_meta_dir: Path, *, refresh: bool = False) -> list[str]:
    api_meta_dir.mkdir(parents=True, exist_ok=True)
    missing = missing_aws_metadata(api_meta_dir)
    if not refresh and not missing:
        return []

    downloaded = []
    for service in (source_services() if refresh else missing):
        version, name, url = latest_model_download(service)
        data = fetch_json(url)
        if not isinstance(data, dict) or not data.get("shapes"):
            raise RuntimeError(f"AWS model is invalid; missing shapes: {service}")
        out = api_meta_dir / service / "service" / version / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        downloaded.append(service)
    return downloaded


def ensure_aws_metadata(api_meta_dir: Path, *, models_dir: Path | None = None, refresh: bool = False) -> list[str]:
    changed = []
    if models_dir and models_dir.exists() and not refresh:
        changed.extend(copy_aws_metadata(api_meta_dir, models_dir, refresh=False))
    changed.extend(download_aws_metadata(api_meta_dir, refresh=refresh))
    return changed
