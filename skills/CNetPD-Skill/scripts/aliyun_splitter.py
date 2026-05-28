"""Small Aliyun OpenAPI metadata splitter used by CNetPD."""

from __future__ import annotations

import copy
import json
import re
import time
from pathlib import Path

VERSION = "2.0.0"

SLUG_MAP = {
    "IPAM多账号管理": "ipam-members",
    "IPAM": "ipam",
    "IPAM作用范围": "ipam-scope",
    "IPAM地址池": "ipam-pool",
    "资源发现": "resource-discovery",
    "资源组": "resource-group",
    "标签": "tag",
    "VPC": "vpc",
    "交换机": "vswitch",
    "路由表": "route-table",
    "安全组": "security-group",
    "负载均衡": "load-balancing",
}

SENSITIVE_KEYS = {"PrivateKey", "PrivateKeyBody", "ClientKey", "CustomDomainPrivateKey"}
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)


def clean_text(value: str) -> str:
    value = re.sub(r"\[([^\]]*)\]\(~~\d+~~\)", r"\1", value)
    value = re.sub(r"\(~~\d+~~\)", "", value)
    return PRIVATE_KEY_RE.sub("[REDACTED_PRIVATE_KEY]", value).strip()


def scrub(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key in SENSITIVE_KEYS else scrub(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, str):
        return clean_text(value)
    return value


def slugify(title: str) -> str:
    if title in SLUG_MAP:
        return SLUG_MAP[title]
    words = re.findall(r"[A-Za-z0-9]+", title)
    if words:
        return "-".join(word.lower() for word in words)
    return "group-" + str(abs(hash(title)) % 100000)


def unique_slug(title: str, used: set[str]) -> str:
    base = slugify(title)
    slug = base
    i = 2
    while slug in used:
        slug = f"{base}-{i}"
        i += 1
    used.add(slug)
    return slug


def is_required(schema: dict) -> bool:
    value = schema.get("required", False)
    return value.lower() == "true" if isinstance(value, str) else bool(value)


def short_desc(schema: dict) -> str:
    desc = clean_text(schema.get("description", "") or "")
    first = next((line.strip() for line in desc.splitlines() if line.strip()), "")
    return first[:117] + "..." if len(first) > 120 else first


def param_view(param: dict) -> dict:
    schema = param.get("schema", {}) if isinstance(param.get("schema"), dict) else {}
    view = {
        "name": param.get("name", ""),
        "in": param.get("in", ""),
        "schema": scrub(copy.deepcopy(schema)),
    }
    if param.get("style"):
        view["style"] = param["style"]
    return {key: value for key, value in view.items() if value not in ("", {}, [])}


def group_param_summary(param: dict) -> dict:
    schema = param.get("schema", {}) if isinstance(param.get("schema"), dict) else {}
    item = {"name": param.get("name", ""), "type": schema.get("type", "string")}
    note = short_desc(schema)
    if note:
        item["note"] = note
    props = schema.get("items", {}).get("properties", {}) if isinstance(schema.get("items"), dict) else {}
    if props:
        item["itemFields"] = list(props.keys())[:12]
    return item


def required_params(api: dict) -> list[str]:
    required = []
    for param in api.get("parameters", []):
        schema = param.get("schema", {}) if isinstance(param.get("schema"), dict) else {}
        if is_required(schema):
            required.append(param.get("name", ""))
    return [item for item in required if item]


def optional_params(api: dict) -> list[dict]:
    items = []
    for param in api.get("parameters", []):
        schema = param.get("schema", {}) if isinstance(param.get("schema"), dict) else {}
        if not is_required(schema):
            items.append(group_param_summary(param))
    return items[:20]


def response_fields(api: dict) -> list[str]:
    fields = []
    responses = api.get("responses", {})
    for response in responses.values():
        schema = response.get("schema", {}) if isinstance(response, dict) else {}
        for name in schema.get("properties", {}):
            if name != "RequestId" and name not in fields:
                fields.append(name)
            if len(fields) >= 20:
                return fields
    return fields


def api_summary(name: str, api: dict, group: str) -> dict:
    item = {
        "name": name,
        "summary": clean_text(api.get("summary") or api.get("title") or ""),
        "operationType": api.get("operationType") or api.get("systemTags", {}).get("operationType"),
        "required": required_params(api),
        "optional": optional_params(api),
        "returns": response_fields(api),
    }
    if api.get("deprecated"):
        item["deprecated"] = True
    error_count = sum(len(v) for v in api.get("errorCodes", {}).values() if isinstance(v, list))
    if error_count:
        item["errorCount"] = error_count
    return {key: value for key, value in item.items() if value not in ("", None, [], {})}


def api_detail(product: str, name: str, api: dict, group: str) -> dict:
    detail = {
        "_layer": "L2",
        "_version": VERSION,
        "provider": "aliyun",
        "product": product,
        "api": name,
        "group": group,
        "title": api.get("title") or api.get("summary") or name,
        "methods": api.get("methods", []),
        "schemes": api.get("schemes", []),
        "security": api.get("security", []),
        "operationType": api.get("operationType") or api.get("systemTags", {}).get("operationType"),
        "deprecated": bool(api.get("deprecated", False)),
        "description": clean_text(api.get("description", "")),
        "parameters": [param_view(param) for param in api.get("parameters", [])],
        "responses": scrub(api.get("responses", {})),
        "errorCodes": scrub(api.get("errorCodes", {})),
    }
    if api.get("responseDemo"):
        detail["responseDemo"] = scrub(api["responseDemo"])
    return {key: value for key, value in detail.items() if value not in ("", None, [], {})}


def collect_api_names(children: list, apis: dict) -> list[str]:
    names = []
    for child in children:
        if isinstance(child, str) and child in apis:
            names.append(child)
        elif isinstance(child, dict):
            names.extend(collect_api_names(child.get("children", []), apis))
    return names


def directory_groups(data: dict) -> list[tuple[str, str, list[str]]]:
    apis = data.get("apis", {})
    groups = []
    used_slugs: set[str] = set()
    seen_apis: set[str] = set()
    for directory in data.get("directories", []):
        if not isinstance(directory, dict):
            continue
        children = collect_api_names(directory.get("children", []), apis)
        if not children:
            continue
        title = directory.get("title") or "未分类"
        slug = unique_slug(title, used_slugs)
        groups.append((slug, title, children))
        seen_apis.update(children)
    leftovers = [name for name in apis if name not in seen_apis]
    if leftovers:
        groups.append((unique_slug("未分类", used_slugs), "未分类", leftovers))
    return groups


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def split_product(source: Path, output_dir: Path) -> dict:
    data = json.loads(source.read_text(encoding="utf-8"))
    product = data.get("info", {}).get("product") or source.stem
    apis = data.get("apis", {})
    stats = {"product": product, "api_count": len(apis), "group_count": 0, "errors": []}
    if not apis:
        stats["errors"].append(f"产品 {product} 没有 API 定义")
        return stats

    product_dir = output_dir / product
    groups_dir = product_dir / "groups"
    apis_dir = product_dir / "apis"
    group_entries = []
    api_to_group = {}
    groups = directory_groups(data)

    for slug, title, names in groups:
        summaries = []
        for name in names:
            api_to_group[name] = slug
            summaries.append(api_summary(name, apis[name], slug))
        write_json(groups_dir / f"{slug}.json", {
            "_layer": "L1",
            "_version": VERSION,
            "provider": "aliyun",
            "product": product,
            "group": slug,
            "title": title,
            "apiCount": len(summaries),
            "apis": summaries,
        })
        group_entries.append({"slug": slug, "title": title, "count": len(summaries)})

    for name, api in apis.items():
        write_json(apis_dir / f"{name}.json", api_detail(product, name, api, api_to_group.get(name, "uncategorized")))

    endpoints = data.get("endpoints", [])
    write_json(product_dir / "index.json", {
        "_layer": "L0",
        "_version": VERSION,
        "provider": "aliyun",
        "product": product,
        "style": data.get("info", {}).get("style", ""),
        "version": data.get("info", {}).get("version", ""),
        "totalApis": len(apis),
        "groups": group_entries,
        "endpoints": endpoints,
    })
    stats["group_count"] = len(groups)
    stats["files_written"] = len(apis) + len(groups) + 1
    return stats


def validate_output(product_dir: Path, source: Path) -> list[str]:
    data = json.loads(source.read_text(encoding="utf-8"))
    expected = set(data.get("apis", {}))
    index_file = product_dir / "index.json"
    if not index_file.exists():
        return ["missing index.json"]
    found = set()
    for group_file in (product_dir / "groups").glob("*.json"):
        group = json.loads(group_file.read_text(encoding="utf-8"))
        found.update(api.get("name") for api in group.get("apis", []))
    missing = sorted(expected - found)
    api_files_missing = sorted(name for name in expected if not (product_dir / "apis" / f"{name}.json").exists())
    issues = []
    if missing:
        issues.append(f"index 中缺少 {len(missing)} 个 API: {missing[:10]}")
    if api_files_missing:
        issues.append(f"缺少 {len(api_files_missing)} 个 L2 文件: {api_files_missing[:10]}")
    return issues


def split_batch(source_dir: Path, output_dir: Path, *, products_filter: set[str], validate: bool = True) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    totals = {"api_count": 0, "group_count": 0, "files_written": 0, "errors": [], "products": []}
    catalog = []
    for source in sorted(source_dir.rglob("*.json")):
        if source.stem not in products_filter:
            continue
        stats = split_product(source, output_dir)
        totals["api_count"] += stats.get("api_count", 0)
        totals["group_count"] += stats.get("group_count", 0)
        totals["files_written"] += stats.get("files_written", 0)
        totals["products"].append(source.stem)
        totals["errors"].extend(stats.get("errors", []))
        if validate and not stats.get("errors"):
            issues = validate_output(output_dir / source.stem, source)
            totals["errors"].extend(f"[{source.stem}] 验证: {issue}" for issue in issues)
        if not stats.get("errors"):
            catalog.append({
                "provider": "aliyun",
                "product": source.stem,
                "apiCount": stats.get("api_count", 0),
                "groupCount": stats.get("group_count", 0),
                "index": f"{source.stem}/index.json",
            })

    write_json(output_dir / "_catalog.json", {
        "_version": VERSION,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "productCount": len(catalog),
        "products": catalog,
    })
    write_json(output_dir / "_report.json", totals)
    return totals
