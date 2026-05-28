"""Build orchestration for CNetPD-Skill."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from .aliyun_splitter import split_batch
from .aws_metadata import ensure_aws_metadata, missing_aws_metadata
from .aws_splitter import split_batch as split_aws_batch
from .constants import ALIYUN_PROVIDER, AWS_PRODUCTS, AWS_PROVIDER, PRODUCT_CODES, PRODUCT_CODES_BY_PROVIDER, SKILL_NAME
from .metadata import download_network_metadata, find_api_meta, missing_metadata
from .skill import build_install_source, build_skill, write_version_file

logger = logging.getLogger("cnetpd_builder")


def missing_splitter_output(output_dir: Path) -> list[str]:
    missing = []
    for provider, products in PRODUCT_CODES_BY_PROVIDER.items():
        provider_dir = output_dir / "providers" / provider
        missing.extend(
            f"{provider}/{product}"
            for product in products
            if not (provider_dir / product / "index.json").exists()
        )
    return missing


def split_network_products(api_meta_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    providers_dir = output_dir / "providers"
    aliyun_output = providers_dir / ALIYUN_PROVIDER
    aws_output = providers_dir / AWS_PROVIDER
    for product in PRODUCT_CODES:
        product_dir = aliyun_output / product
        if product_dir.exists():
            shutil.rmtree(product_dir)
    for product in PRODUCT_CODES_BY_PROVIDER[AWS_PROVIDER]:
        product_dir = aws_output / product
        if product_dir.exists():
            shutil.rmtree(product_dir)
    aliyun_result = split_batch(api_meta_dir / ALIYUN_PROVIDER, aliyun_output, products_filter=set(PRODUCT_CODES), validate=True)
    aws_result = split_aws_batch(api_meta_dir / AWS_PROVIDER, aws_output, products=AWS_PRODUCTS, validate=True)
    errors = [*aliyun_result.get("errors", []), *aws_result.get("errors", [])]
    if errors:
        raise RuntimeError(f"splitter validation failed: {errors[:5]}")


def copy_legacy_aliyun_metadata(api_meta_dir: Path) -> list[str]:
    copied = []
    target_root = api_meta_dir / ALIYUN_PROVIDER
    for product in PRODUCT_CODES:
        if find_api_meta(target_root, product) is not None:
            continue
        source = find_api_meta(api_meta_dir, product)
        if source is None:
            continue
        target = target_root / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(product)
    return copied


def prepare_data(api_meta_dir: Path, output_dir: Path, *, refresh_meta: bool = False, aws_models_dir: Path | None = None) -> None:
    missing_output = missing_splitter_output(output_dir)
    missing_meta = missing_metadata(api_meta_dir / ALIYUN_PROVIDER)
    missing_aws = missing_aws_metadata(api_meta_dir / AWS_PROVIDER)
    if missing_output:
        logger.info("missing splitter output: %s", missing_output)
    if missing_meta and not refresh_meta:
        copied = copy_legacy_aliyun_metadata(api_meta_dir)
        if copied:
            logger.info("copied legacy Aliyun metadata into provider cache: %s", copied)
            missing_meta = missing_metadata(api_meta_dir / ALIYUN_PROVIDER)
    if refresh_meta or missing_meta:
        if missing_meta:
            logger.info("missing metadata: %s", missing_meta)
        downloaded = download_network_metadata(api_meta_dir / ALIYUN_PROVIDER, refresh=refresh_meta)
        if downloaded:
            logger.info("downloaded metadata: %s", downloaded)
    if refresh_meta or missing_aws:
        if missing_aws:
            logger.info("missing AWS metadata: %s", missing_aws)
        updated = ensure_aws_metadata(api_meta_dir / AWS_PROVIDER, models_dir=aws_models_dir, refresh=refresh_meta)
        if updated:
            logger.info("updated AWS metadata: %s", updated)
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
    aws_models_dir: Path | None = None,
    force: bool = False,
) -> dict:
    if not no_prepare:
        prepare_data(api_meta_dir, output_dir, refresh_meta=refresh_meta, aws_models_dir=aws_models_dir)
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
