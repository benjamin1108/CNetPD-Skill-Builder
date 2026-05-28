#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Runtime query tool for CNetPD-Skill."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

PACKAGED_DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
CACHE_DATA_ROOT = Path(os.environ.get(
    "CNETPD_CACHE_DIR",
    Path.home() / ".cache" / "cnetpd-skill" / "data",
)).expanduser()
SYNC_SCRIPT = Path(__file__).resolve().parent / "sync_data.py"
DEFAULT_PROVIDER = "aliyun"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def valid_data_root(root: Path) -> bool:
    return (root / "_cnetpd-index.json").exists() and (root / "_manifest.json").exists()


def manifest(root: Path) -> dict:
    try:
        return read_json(root / "_manifest.json")
    except (OSError, json.JSONDecodeError):
        return {}


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def sync_ttl() -> timedelta:
    try:
        return timedelta(days=max(1, int(os.environ.get("CNETPD_SYNC_TTL_DAYS", "7"))))
    except ValueError:
        return timedelta(days=7)


def stale(root: Path) -> bool:
    generated_at = parse_dt(manifest(root).get("generated_at"))
    if generated_at is None:
        return True
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - generated_at > sync_ttl()


def auto_sync_enabled() -> bool:
    return os.environ.get("CNETPD_AUTO_SYNC", "1").lower() not in {"0", "false", "no", "off"}


def attempt_file() -> Path:
    return CACHE_DATA_ROOT.parent / ".last_sync_attempt"


def recent_attempt() -> bool:
    try:
        last = parse_dt(attempt_file().read_text(encoding="utf-8").strip())
    except OSError:
        return False
    return bool(last and datetime.now(timezone.utc) - last < timedelta(hours=6))


def mark_attempt() -> None:
    path = attempt_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")


def run_sync(*, quiet: bool, force: bool = False) -> bool:
    if not SYNC_SCRIPT.exists():
        return False
    cmd = [sys.executable, str(SYNC_SCRIPT), "--target", str(CACHE_DATA_ROOT)]
    if force:
        cmd.append("--force")
    if quiet:
        cmd.append("--quiet")
    result = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE if quiet else None,
        stderr=subprocess.PIPE if quiet else None,
    )
    return result.returncode == 0


def maybe_auto_sync() -> None:
    if os.environ.get("CNETPD_DATA") or not auto_sync_enabled():
        return
    if valid_data_root(CACHE_DATA_ROOT) and not stale(CACHE_DATA_ROOT):
        return
    if recent_attempt():
        return
    try:
        mark_attempt()
        run_sync(quiet=True, force=not valid_data_root(CACHE_DATA_ROOT))
    except OSError:
        return


def select_data_root() -> tuple[str, Path]:
    override = os.environ.get("CNETPD_DATA")
    if override:
        return "override", Path(override).expanduser()
    maybe_auto_sync()
    if valid_data_root(CACHE_DATA_ROOT):
        return "cache", CACHE_DATA_ROOT
    return "packaged", PACKAGED_DATA_ROOT


DATA_SOURCE, DATA_ROOT = select_data_root()


def index() -> dict:
    return read_json(DATA_ROOT / "_cnetpd-index.json")


def product_dir(product: str, provider: str) -> Path | None:
    root = DATA_ROOT / "providers" / provider
    if not root.exists():
        return None
    needle = product.lower()
    for path in root.iterdir():
        if path.is_dir() and path.name.lower() == needle:
            return path
    return None


def cmd_domain() -> None:
    idx = index()
    print(f"Skill: {idx['skill']}  |  Domain: {idx['domain']}")
    print(f"Providers: {len(idx['providers'])}  |  Products: {idx['productCount']}  |  Topics: {idx['topicCount']}\n")
    print("【Providers】")
    for provider in idx["providers"]:
        print(f"  {provider['slug']:<10} {provider['display']}  {provider['productCount']} products")
    print("\n【Topics】")
    for topic in idx["topics"]:
        products = "、".join(f"{p['provider']}/{p['product']}" for p in topic["products"])
        print(f"  {topic['slug']:<18} {topic['title']}  {products}")


def cmd_providers() -> None:
    for provider in index()["providers"]:
        print(f"{provider['slug']:<10} {provider['display']}  {provider['productCount']} products")


def cmd_topics() -> None:
    for topic in index()["topics"]:
        print(f"{topic['slug']:<18} {topic['title']}")
        print(f"  {topic['description']}\n")


def cmd_topic(slug: str) -> None:
    idx = index()
    topic = next((item for item in idx["topics"] if item["slug"] == slug), None)
    if not topic:
        print("可用主题: " + ", ".join(item["slug"] for item in idx["topics"]))
        return
    print(f"【{topic['title']}】{topic['description']}\n")
    print("候选产品:")
    for item in topic["products"]:
        print(f"  {item['provider']}/{item['product']:<24} {item['role']}")
    print("\n选型决策:")
    for decision in topic["decisions"]:
        print(f"  - 当 {decision['when']} -> {decision['use']}")
    relevant = topic.get("relevantApis", {})
    if relevant:
        print("\n相关 API:")
        for key, apis in relevant.items():
            print(f"  {key}: " + ", ".join(api["api"] for api in apis[:8]))


def cmd_product(product: str, provider: str) -> None:
    root = product_dir(product, provider)
    if not root:
        print(f"未找到产品: {provider}/{product}")
        return
    data = read_json(root / "index.json")
    print(f"产品: {provider}/{data.get('product', product)}  |  {data.get('totalApis', '?')} APIs\n")
    print(f"{'Slug':<24} {'能力分区':<20} {'API数':>5}")
    print("-" * 56)
    for group in data.get("groups", []):
        print(f"{group['slug']:<24} {group['title']:<20} {group['count']:>5}")


def cmd_group(slug: str, product: str, provider: str) -> None:
    root = product_dir(product, provider)
    if not root:
        print(f"未找到产品: {provider}/{product}")
        return
    group_file = root / "groups" / f"{slug}.json"
    if not group_file.exists():
        print(f"未找到分区: {slug}")
        return
    group = read_json(group_file)
    print(f"【{group['title']}】{provider}/{product}  {len(group['apis'])} APIs\n")
    for api in group["apis"]:
        print(f"  {api['name']} [{api.get('operationType', '')}]")
        print(f"    {api.get('summary', '')}")
        if api.get("required"):
            print(f"    必填: {', '.join(api['required'])}")


def cmd_search(keyword: str, provider: str | None) -> None:
    kw = keyword.lower()
    providers = [provider] if provider else [item["slug"] for item in index()["providers"]]
    total = 0
    for provider_slug in providers:
        root = DATA_ROOT / "providers" / provider_slug
        if not root.exists():
            continue
        for product in sorted(path.name for path in root.iterdir() if path.is_dir()):
            hits = []
            for group_file in sorted((root / product / "groups").glob("*.json")):
                group = read_json(group_file)
                for api in group.get("apis", []):
                    haystack = f"{api.get('name', '')} {api.get('summary', '')}".lower()
                    if kw in haystack:
                        hits.append((group.get("group", group_file.stem), api))
            if hits:
                print(f"\n【{provider_slug}/{product}】{len(hits)} matches")
                for group, api in hits[:15]:
                    print(f"  {api['name']} ({group}) - {api.get('summary', '')}")
                total += len(hits)
    if total == 0:
        print(f"未找到: {keyword}")


def print_param(param: dict) -> None:
    schema = param.get("schema", {})
    name = param.get("name", "")
    typ = schema.get("type", "")
    loc = f" ({param.get('in')})" if param.get("in") else ""
    print(f"  {name}: {typ}{loc}")
    desc = schema.get("description")
    if desc:
        print(f"      {desc.splitlines()[0][:120]}")


def cmd_detail(api_name: str, product: str, provider: str, full: bool = False) -> None:
    root = product_dir(product, provider)
    if not root:
        print(f"未找到产品: {provider}/{product}")
        return
    api_file = root / "apis" / f"{api_name}.json"
    if not api_file.exists():
        candidates = [path.stem for path in (root / "apis").glob("*.json") if api_name.lower() in path.stem.lower()]
        print("候选: " + ", ".join(candidates[:10]) if candidates else f"未找到 API: {api_name}")
        return
    api = read_json(api_file)
    print(f"能力: {provider}/{product}/{api.get('api', api_name)}")
    print(f"分区: {api.get('group', '')}")
    print(f"标题: {api.get('title', '')}")
    if api.get("deprecated"):
        print("状态: 已废弃")
    desc = api.get("description", "")
    if desc:
        lines = [line.strip() for line in desc.splitlines() if line.strip()]
        print("\n说明:")
        for line in lines[:20 if full else 6]:
            print(f"  {line}")
    params = api.get("parameters", [])
    if params:
        print("\n参数:")
        for param in params[:50 if full else 20]:
            print_param(param)
    fields = []
    for response in api.get("responses", {}).values():
        schema = response.get("schema", {}) if isinstance(response, dict) else {}
        fields.extend(name for name in schema.get("properties", {}) if name != "RequestId")
    if fields:
        print("\n返回字段: " + ", ".join(dict.fromkeys(fields)))


def cmd_constraints(api_name: str, product: str, provider: str) -> None:
    root = product_dir(product, provider)
    api_file = root / "apis" / f"{api_name}.json" if root else None
    if not api_file or not api_file.exists():
        print(f"未找到 API: {provider}/{product}/{api_name}")
        return
    api = read_json(api_file)
    grouped = defaultdict(list)
    for status, errors in api.get("errorCodes", {}).items():
        for error in errors if isinstance(errors, list) else []:
            code = error.get("errorCode", "") if isinstance(error, dict) else str(error)
            grouped[status].append(code)
    for status, codes in grouped.items():
        print(f"{status}:")
        for code in codes:
            print(f"  {code}")


def cmd_data_info() -> None:
    meta = manifest(DATA_ROOT)
    print(f"数据源: {DATA_SOURCE}")
    print(f"路径: {DATA_ROOT}")
    print(f"生成时间: {meta.get('generated_at', 'unknown')}")
    print(f"schema: {meta.get('schema_version', 'unknown')}")
    print(f"providers: {', '.join(meta.get('providers', []))}")
    print(f"文件数: {meta.get('file_count', 'unknown')}")
    if DATA_SOURCE == "cache":
        print(f"缓存状态: {'过期' if stale(DATA_ROOT) else '新鲜'}")
    print(f"缓存目录: {CACHE_DATA_ROOT}")


def main() -> None:
    parser = argparse.ArgumentParser(description="CNetPD-Skill query tool")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("domain")
    sub.add_parser("providers")
    sub.add_parser("topics")
    topic = sub.add_parser("topic"); topic.add_argument("slug")
    product = sub.add_parser("product"); product.add_argument("product"); product.add_argument("--provider", default=DEFAULT_PROVIDER)
    group = sub.add_parser("group"); group.add_argument("slug"); group.add_argument("--product", required=True); group.add_argument("--provider", default=DEFAULT_PROVIDER)
    search = sub.add_parser("search"); search.add_argument("keyword"); search.add_argument("--provider")
    detail = sub.add_parser("detail"); detail.add_argument("api_name"); detail.add_argument("--product", required=True); detail.add_argument("--provider", default=DEFAULT_PROVIDER); detail.add_argument("--full", action="store_true")
    constraints = sub.add_parser("constraints"); constraints.add_argument("api_name"); constraints.add_argument("--product", required=True); constraints.add_argument("--provider", default=DEFAULT_PROVIDER)
    sub.add_parser("data-info")
    sync = sub.add_parser("sync"); sync.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return
    if args.command != "sync" and not valid_data_root(DATA_ROOT):
        raise SystemExit(f"数据目录无效: {DATA_ROOT}")
    dispatch = {
        "domain": lambda: cmd_domain(),
        "providers": lambda: cmd_providers(),
        "topics": lambda: cmd_topics(),
        "topic": lambda: cmd_topic(args.slug),
        "product": lambda: cmd_product(args.product, args.provider),
        "group": lambda: cmd_group(args.slug, args.product, args.provider),
        "search": lambda: cmd_search(args.keyword, args.provider),
        "detail": lambda: cmd_detail(args.api_name, args.product, args.provider, args.full),
        "constraints": lambda: cmd_constraints(args.api_name, args.product, args.provider),
        "data-info": lambda: cmd_data_info(),
        "sync": lambda: sys.exit(0 if run_sync(quiet=False, force=args.force) else 1),
    }
    dispatch[args.command]()


if __name__ == "__main__":
    main()
