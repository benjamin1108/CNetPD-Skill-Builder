"""Build orchestration for CNetPD-Skill."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from .aliyun_splitter import split_batch
from .constants import PRODUCT_CODES, SKILL_NAME
from .metadata import download_network_metadata, missing_metadata
from .skill import build_install_source, build_skill, write_version_file

logger = logging.getLogger("cnetpd_builder")


def missing_splitter_output(output_dir: Path) -> list[str]:
    return [product for product in PRODUCT_CODES if not (output_dir / product / "index.json").exists()]


def split_network_products(api_meta_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for product in PRODUCT_CODES:
        product_dir = output_dir / product
        if product_dir.exists():
            shutil.rmtree(product_dir)
    result = split_batch(api_meta_dir, output_dir, products_filter=set(PRODUCT_CODES), validate=True)
    if result.get("errors"):
        raise RuntimeError(f"splitter validation failed: {result['errors'][:5]}")


def prepare_data(api_meta_dir: Path, output_dir: Path, *, refresh_meta: bool = False) -> None:
    missing_output = missing_splitter_output(output_dir)
    missing_meta = missing_metadata(api_meta_dir)
    if missing_output:
        logger.info("missing splitter output: %s", missing_output)
    if refresh_meta or missing_meta:
        if missing_meta:
            logger.info("missing metadata: %s", missing_meta)
        downloaded = download_network_metadata(api_meta_dir, refresh=refresh_meta)
        if downloaded:
            logger.info("downloaded metadata: %s", downloaded)
    split_network_products(api_meta_dir, output_dir)
    missing_after = missing_splitter_output(output_dir)
    if missing_after:
        raise RuntimeError("network data is incomplete: " + ", ".join(missing_after))


def build(
    *,
    api_meta_dir: Path,
    output_dir: Path,
    target_dir: Path,
    install_source_dir: Path | None,
    repo_version_file: Path | None,
    package_dir: Path,
    no_prepare: bool = False,
    refresh_meta: bool = False,
    force: bool = False,
) -> dict:
    if not no_prepare:
        prepare_data(api_meta_dir, output_dir, refresh_meta=refresh_meta)
    elif not output_dir.is_dir():
        raise SystemExit(f"source dir does not exist: {output_dir}")
    result = build_skill(output_dir, target_dir, force=force, package_dir=package_dir)
    if install_source_dir is not None:
        install_result = build_install_source(
            output_dir,
            install_source_dir,
            force=True,
            package_dir=package_dir,
        )
        result["install_source"] = install_result["target"]
    if repo_version_file is not None:
        version_path = write_version_file(repo_version_file.parent)
        if version_path != repo_version_file:
            version_path.replace(repo_version_file)
        result["repo_version"] = str(repo_version_file)
    logger.info("%s built at %s", SKILL_NAME, target_dir)
    return result
