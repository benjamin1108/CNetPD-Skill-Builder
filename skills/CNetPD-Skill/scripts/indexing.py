"""Build the provider-aware CNetPD data index."""

from __future__ import annotations

import json
from pathlib import Path

try:
    from .constants import ALL_PRODUCTS, PROJECT_DESCRIPTION, PROJECT_NAME, PROVIDERS, SKILL_NAME, SKILL_VERSION, TOPICS
except ImportError:  # Runtime copy lives directly under scripts/.
    from cnetpd_constants import ALL_PRODUCTS, PROJECT_DESCRIPTION, PROJECT_NAME, PROVIDERS, SKILL_NAME, SKILL_VERSION, TOPICS  # type: ignore


def provider_meta(provider: str) -> dict:
    return next(item for item in PROVIDERS if item["slug"] == provider)


def product_meta(provider: str, product: str) -> dict | None:
    return next(
        (
            item
            for item in ALL_PRODUCTS
            if item["provider"] == provider and item["product"].lower() == product.lower()
        ),
        None,
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def expand_topic_apis(topic: dict, data_dir: Path, max_per_product: int = 8) -> dict:
    result: dict[str, list[dict]] = {}
    keywords = [keyword.lower() for keyword in topic.get("keywords", [])]
    if not keywords:
        return result
    for ref in topic.get("products", []):
        provider = ref["provider"]
        product = ref["product"]
        groups_dir = data_dir / "providers" / provider / product / "groups"
        if not groups_dir.exists():
            continue
        matches = []
        for group_file in sorted(groups_dir.glob("*.json")):
            group = read_json(group_file)
            for api in group.get("apis", []):
                haystack = f"{api.get('name', '')} {api.get('summary', '')}".lower()
                if any(keyword in haystack for keyword in keywords):
                    matches.append({
                        "api": api.get("name", ""),
                        "group": group.get("group", group_file.stem),
                        "summary": api.get("summary", ""),
                    })
                    if len(matches) >= max_per_product:
                        break
            if len(matches) >= max_per_product:
                break
        if matches:
            result[f"{provider}/{product}"] = matches
    return result


def product_entry(meta: dict, product_dir: Path) -> dict:
    api_count = 0
    group_count = 0
    source_service = meta.get("sourceService", meta["product"])
    if (product_dir / "index.json").exists():
        index = read_json(product_dir / "index.json")
        api_count = index.get("totalApis", 0)
        group_count = len(index.get("groups", []))
        source_service = index.get("sourceService", source_service)
    return {
        "provider": meta["provider"],
        "product": meta["product"],
        "sourceService": source_service,
        "slug": meta["product"].lower(),
        "display": meta["display"],
        "summary": meta["summary"],
        "coverage": meta["coverage"],
        "apiCount": api_count,
        "groupCount": group_count,
    }


def build_cnetpd_index(data_dir: Path) -> dict:
    products = [
        product_entry(meta, data_dir / "providers" / meta["provider"] / meta["product"])
        for meta in ALL_PRODUCTS
    ]
    topics = []
    for topic in TOPICS:
        item = {
            "slug": topic["slug"],
            "title": topic["title"],
            "description": topic["description"],
            "products": topic["products"],
            "decisions": [{"when": when, "use": use} for when, use in topic["decisions"]],
        }
        relevant = expand_topic_apis(topic, data_dir)
        if relevant:
            item["relevantApis"] = relevant
        topics.append(item)
    provider_entries = []
    for provider in PROVIDERS:
        provider_entries.append({
            "slug": provider["slug"],
            "display": provider["display"],
            "productCount": len(provider["products"]),
        })
    return {
        "_layer": "L-1",
        "_version": SKILL_VERSION,
        "skill": SKILL_NAME,
        "project": PROJECT_NAME,
        "domain": "cloud-networking",
        "description": PROJECT_DESCRIPTION,
        "providers": provider_entries,
        "productCount": len(products),
        "topicCount": len(topics),
        "products": products,
        "topics": topics,
    }
