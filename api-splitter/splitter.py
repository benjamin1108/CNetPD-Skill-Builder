#!/usr/bin/env python3
"""
阿里云 API 元数据渐进披露拆分器 (Progressive Disclosure Splitter)

将阿里云 OpenAPI 的单体 api-docs.json 拆分为三层渐进结构，
专为 LLM Skills 查询场景优化。

三层设计:
  L0 - index.json       产品索引：分类目录 + 每个API一句话摘要 (~3-8KB)
  L1 - groups/{g}.json  分组概览：该组所有API的参数签名 + 返回字段 (~1-15KB/组)
  L2 - apis/{A}.json    完整详情：参数描述 + 响应结构 + 错误码 + 示例 (~2-33KB/API)

查询路径:
  skill 读 index.json → 定位到某个 group → 读 groups/xxx.json → 定位到某个 API
  → 读 apis/XxxYyy.json → 获得完整调用信息

用法:
  python splitter.py <source.json> [--output-dir <dir>] [--validate] [--dry-run]

示例:
  python splitter.py ../api_metadata/网络与CDN/专有网络/Vpc.json
  python splitter.py ../api_metadata/网络与CDN/专有网络/Vpc.json --output-dir ../output_v2
  python splitter.py ../api_metadata/网络与CDN/专有网络/Vpc.json --validate --verbose
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants & Config
# ---------------------------------------------------------------------------

VERSION = "2.0.0"
logger = logging.getLogger("api_splitter")

# L2 schema 中要剔除的低价值字段
STRIP_SCHEMA_KEYS = {"title", "docRequired", "isFileTransferUrl", "readOnly"}

# systemTags 中对调用无关的字段
STRIP_SYSTEM_TAG_KEYS = {
    "abilityTreeCode", "abilityTreeNodes",
    "autoTest", "notSupportAutoTestReason",
    "tenantRelevance",
}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@dataclass
class SplitStats:
    """拆分统计"""
    source_bytes: int = 0
    api_count: int = 0
    group_count: int = 0
    files_written: int = 0
    l0_bytes: int = 0
    l1_bytes: int = 0
    l2_bytes: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_output_bytes(self) -> int:
        return self.l0_bytes + self.l1_bytes + self.l2_bytes

    def summary(self) -> dict:
        return {
            "version": VERSION,
            "source_bytes": self.source_bytes,
            "output_bytes": self.total_output_bytes,
            "ratio": f"{self.total_output_bytes / max(self.source_bytes, 1) * 100:.1f}%",
            "api_count": self.api_count,
            "group_count": self.group_count,
            "files_written": self.files_written,
            "layer_bytes": {
                "L0_index": self.l0_bytes,
                "L1_groups": self.l1_bytes,
                "L2_apis": self.l2_bytes,
            },
            "errors": self.errors[:20],
            "warnings": self.warnings[:20],
        }


# ---------------------------------------------------------------------------
# $ref Resolver
# ---------------------------------------------------------------------------


class RefResolver:
    """解析 $ref 引用，将 components.schemas 中的定义内联展开"""

    def __init__(self, schemas: dict[str, Any]):
        self._schemas = schemas
        self._cache: dict[str, Any] = {}
        self._resolving: set[str] = set()

    def resolve(self, obj: Any, depth: int = 10) -> Any:
        if depth <= 0:
            return obj
        if isinstance(obj, dict):
            if "$ref" in obj:
                return self._resolve_ref(obj["$ref"], depth - 1)
            return {k: self.resolve(v, depth) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.resolve(item, depth) for item in obj]
        return obj

    def _resolve_ref(self, ref: str, depth: int) -> Any:
        if ref in self._cache:
            return copy.deepcopy(self._cache[ref])
        if ref in self._resolving:
            return {"$ref": ref, "_circular": True}

        parts = ref.lstrip("#/").split("/")
        if len(parts) >= 3 and parts[0] == "components" and parts[1] == "schemas":
            name = "/".join(parts[2:])
            if name in self._schemas:
                self._resolving.add(ref)
                resolved = self.resolve(copy.deepcopy(self._schemas[name]), depth)
                self._resolving.discard(ref)
                self._cache[ref] = resolved
                return copy.deepcopy(resolved)

        return {"$ref": ref, "_unresolved": True}


# ---------------------------------------------------------------------------
# Text Utilities
# ---------------------------------------------------------------------------


def clean_description(desc: str) -> str:
    """清理描述文本中的内部标记"""
    if not desc:
        return desc
    # [text](~~12345~~) → text
    cleaned = re.sub(r"\[([^\]]*)\]\(~~\d+~~\)", r"\1", desc)
    # 裸 (~~12345~~)
    cleaned = re.sub(r"\(~~\d+~~\)", "", cleaned)
    # <props="china">...</props>
    cleaned = re.sub(r'<props="[^"]*">(.*?)</props>', r"\1", cleaned, flags=re.DOTALL)
    return cleaned.strip()


def extract_first_sentence(text: str, max_len: int = 80) -> str:
    """提取第一句话作为摘要"""
    if not text:
        return ""
    clean = clean_description(text)
    # 取第一行
    line = clean.split("\n")[0].strip()
    # 取第一句 (句号/分号)
    for sep in ("。", "；", "。", "\n"):
        idx = line.find(sep)
        if 0 < idx < max_len:
            line = line[:idx + 1]
            break
    if len(line) > max_len:
        line = line[:max_len - 3] + "..."
    return line


def slugify(title: str) -> str:
    """
    将中文分类标题转为英文 slug 文件名。
    使用已知的映射表 + fallback 拼音首字母。
    """
    title = title.strip()

    # 已知映射 (覆盖 Vpc.json 的 37 个分类)
    mapping = {
        "专有网络（VPC）": "vpc",
        "专有网络(VPC)": "vpc",
        "路由器": "vrouter",
        "交换机": "vswitch",
        "路由表": "route-table",
        "前缀列表": "prefix-list",
        "DHCP选项集": "dhcp-option-set",
        "流日志": "flow-log",
        "网络ACL": "network-acl",
        "高可用虚拟IP": "havip",
        "流量镜像": "traffic-mirror",
        "路由目标组": "route-target-group",
        "弹性公网IP": "eip",
        "共享带宽": "shared-bandwidth",
        "物理专线": "physical-connection",
        "故障演练": "fault-simulation",
        "QoS策略": "qos-policy",
        "边界路由器": "virtual-border-router",
        "BGP": "bgp",
        "NAT": "nat",
        "IPv4网关": "ipv4-gateway",
        "VPN网关": "vpn-gateway",
        "用户网关": "customer-gateway",
        "绑定VPN网关实例": "vpn-attachment",
        "绑定转发路由器实例": "vpn-route-entry",
        "SSL客户端": "ssl-client",
        "SSL服务端": "ssl-server",
        "IPsec服务端": "ipsec-server",
        "IPv6网关": "ipv6-gateway",
        "IPv6转换服务": "ipv6-translation",
        "地域": "region",
        "标签": "tag",
        "路由器接口": "router-interface",
        "高速上云服务": "express-connect",
        "全球加速实例": "global-acceleration",
        "网关终端节点": "gateway-endpoint",
        "资源组": "resource-group",
        "其他": "misc",
    }

    if title in mapping:
        return mapping[title]

    # Fallback: 如果标题本身是英文/数字，直接 kebab-case
    ascii_part = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").lower()
    if ascii_part and len(ascii_part) > 2:
        return ascii_part

    # 最终 fallback: hash
    import hashlib
    return "group-" + hashlib.md5(title.encode()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Schema Cleaning (for L2)
# ---------------------------------------------------------------------------


def clean_schema(schema: dict) -> dict:
    """递归清理 schema，去除低价值字段"""
    if not isinstance(schema, dict):
        return schema

    result = {}
    for k, v in schema.items():
        if k in STRIP_SCHEMA_KEYS:
            continue
        if k == "description" and isinstance(v, str):
            result[k] = clean_description(v)
        elif k == "items" and isinstance(v, dict):
            result[k] = clean_schema(v)
        elif k == "properties" and isinstance(v, dict):
            result[k] = {pk: clean_schema(pv) for pk, pv in v.items()}
        else:
            result[k] = v
    return result


# ---------------------------------------------------------------------------
# L0 Builder: Product Index
# ---------------------------------------------------------------------------


def build_index(data: dict) -> dict:
    """
    构建 L0 index.json — 产品级索引。

    目标: skill 读这一个文件就能快速判断要查哪个分组。
    极致精简: 每个 group 只保留 slug + title + count，
    具体 API 列表在 L1 groups/{slug}.json 中按需加载。
    """
    info = data.get("info", {})
    product = info.get("product", "unknown")
    style = info.get("style", "unknown")
    api_version = info.get("version", "")

    directories = data.get("directories", [])
    apis = data.get("apis", {})

    # 构建分组列表 (只保留 slug + title + count)
    groups = []
    all_listed = set()
    for dir_entry in directories:
        if not isinstance(dir_entry, dict):
            continue
        title = dir_entry.get("title", "").strip()
        children = dir_entry.get("children", [])
        api_names = _flatten_children(children)
        slug = slugify(title)

        # 统计有效 API 数量
        valid_names = [n for n in api_names if n in apis]
        all_listed.update(valid_names)

        groups.append({
            "slug": slug,
            "title": title,
            "count": len(valid_names),
        })

    # 处理不在任何 directory 中的 API (orphans)
    orphans = [n for n in apis if n not in all_listed]
    if orphans:
        groups.append({
            "slug": "uncategorized",
            "title": "未分类",
            "count": len(orphans),
        })

    # Endpoints 精简: 只保留 regionId → endpoint 映射
    endpoints = data.get("endpoints", [])
    endpoint_map = {}
    for ep in endpoints:
        rid = ep.get("regionId", "")
        url = ep.get("endpoint", "")
        if rid and url:
            endpoint_map[rid] = url

    index = {
        "_layer": "L0",
        "_version": VERSION,
        "product": product,
        "style": style,
        "apiVersion": api_version,
        "totalApis": sum(g["count"] for g in groups),
        "groups": groups,
    }
    if endpoint_map:
        index["endpoints"] = endpoint_map

    return index


def _flatten_children(children: list) -> list[str]:
    """递归展平 directory children"""
    result = []
    for item in children:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            result.extend(_flatten_children(item.get("children", [])))
    return result


# ---------------------------------------------------------------------------
# L1 Builder: Group Overview
# ---------------------------------------------------------------------------


def build_group(
    slug: str,
    title: str,
    api_names: list[str],
    apis: dict,
    *,
    product: str,
    style: str,
    resolver: RefResolver | None,
) -> dict:
    """
    构建 L1 groups/{slug}.json — 分组级概览。

    目标: 足够判断该用哪个 API，但不含完整描述。
    每个 API 保留: summary, 必填参数名, 可选参数摘要, 返回字段名列表。
    """
    is_roa = style in ("ROA", "V3")

    api_overviews = []
    for name in api_names:
        api_obj = apis.get(name)
        if not api_obj or not isinstance(api_obj, dict):
            continue

        if resolver:
            api_obj = resolver.resolve(api_obj)

        overview: dict[str, Any] = {
            "name": name,
            "summary": api_obj.get("summary", ""),
        }

        # ROA 路径
        if is_roa and "path" in api_obj:
            overview["method"] = (api_obj.get("methods") or [""])[0].upper()
            overview["path"] = api_obj["path"]

        # 操作类型
        sys_tags = api_obj.get("systemTags", {})
        op_type = sys_tags.get("operationType") or api_obj.get("operationType", "")
        if op_type:
            overview["operationType"] = op_type

        # 废弃标记
        if api_obj.get("deprecated"):
            overview["deprecated"] = True

        # 参数签名
        params = api_obj.get("parameters", [])
        req_params, opt_params = _extract_param_signature(params, is_roa=is_roa)
        if req_params:
            overview["required"] = req_params
        if opt_params:
            overview["optional"] = opt_params

        # 返回字段名
        responses = api_obj.get("responses", {})
        ret_fields = _extract_return_fields(responses)
        if ret_fields:
            overview["returns"] = ret_fields

        # 错误码计数
        error_codes = api_obj.get("errorCodes", {})
        err_count = sum(
            len(errs) for errs in error_codes.values() if isinstance(errs, list)
        )
        if err_count:
            overview["errorCount"] = err_count

        api_overviews.append(overview)

    return {
        "_layer": "L1",
        "_version": VERSION,
        "product": product,
        "group": slug,
        "title": title,
        "apiCount": len(api_overviews),
        "apis": api_overviews,
    }


def _extract_param_signature(
    parameters: list[dict], *, is_roa: bool = False
) -> tuple[list[str], list[dict]]:
    """
    提取参数签名。
    required: 只留名字列表
    optional: name + type + 一句话 note + enum(如有)
    """
    required = []
    optional = []

    for param in parameters:
        name = param.get("name", "")
        schema = param.get("schema", {})
        if not isinstance(schema, dict):
            continue

        in_loc = param.get("in", "")

        # ROA body 展开
        if in_loc == "body" and schema.get("type") == "object":
            props = schema.get("properties", {})
            for fname, fschema in props.items():
                if not isinstance(fschema, dict):
                    continue
                is_req = _is_required(fschema)
                if is_req:
                    required.append(fname)
                else:
                    opt = _build_opt_entry(fname, fschema)
                    if opt:
                        optional.append(opt)
            continue

        is_req = _is_required(schema)
        if is_req:
            required.append(name)
        else:
            opt = _build_opt_entry(name, schema)
            if opt:
                optional.append(opt)

    return required, optional


def _is_required(schema: dict) -> bool:
    val = schema.get("required", False)
    if isinstance(val, str):
        return val.lower() == "true"
    return bool(val)


def _is_deprecated(schema: dict) -> bool:
    if schema.get("deprecated"):
        return True
    desc = schema.get("description", "")
    if not desc:
        return False
    return bool(re.search(r"(该字段|该参数)已废弃", desc[:60]))


def _build_opt_entry(name: str, schema: dict) -> dict | None:
    """构建可选参数的精简条目"""
    if _is_deprecated(schema):
        return None

    entry: dict[str, Any] = {"name": name, "type": schema.get("type", "string")}

    # 枚举
    enum_titles = schema.get("enumValueTitles")
    enum_vals = schema.get("enum")
    if enum_titles:
        entry["enum"] = list(enum_titles.keys())
    elif enum_vals and len(enum_vals) <= 20:
        entry["enum"] = enum_vals

    # 默认值
    default = schema.get("default")
    if default is not None:
        entry["default"] = default

    # 一句话注释
    note = extract_first_sentence(schema.get("description", ""), max_len=60)
    if note:
        entry["note"] = note

    # 数组 items 类型提示
    if entry["type"] == "array":
        items = schema.get("items", {})
        if isinstance(items, dict):
            if items.get("type") == "object":
                props = items.get("properties", {})
                entry["itemFields"] = list(props.keys())[:20]
            else:
                entry["itemType"] = items.get("type", "string")

    return entry


def _extract_return_fields(responses: dict, max_depth: int = 2) -> list[str]:
    """提取响应的顶层字段名"""
    fields = []
    for code, resp in responses.items():
        schema = resp.get("schema", {})
        if isinstance(schema, dict):
            props = schema.get("properties", {})
            for k in props:
                if k not in fields and k != "RequestId":
                    fields.append(k)
    return fields


# ---------------------------------------------------------------------------
# L2 Builder: Full API Detail
# ---------------------------------------------------------------------------


def build_api_detail(
    api_name: str,
    api_obj: dict,
    *,
    product: str,
    style: str,
    group_slug: str,
) -> dict:
    """
    构建 L2 apis/{ApiName}.json — 完整 API 调用详情。

    包含: 描述, 完整参数(含 description), 响应结构, 错误码, 示例。
    这是调用 API 所需的一切信息。
    """
    is_roa = style in ("ROA", "V3")

    detail: dict[str, Any] = {
        "_layer": "L2",
        "_version": VERSION,
        "product": product,
        "api": api_name,
        "group": group_slug,
        "title": api_obj.get("title", ""),
    }

    # 协议信息
    if api_obj.get("methods"):
        detail["methods"] = api_obj["methods"]
    if api_obj.get("schemes"):
        detail["schemes"] = api_obj["schemes"]
    if is_roa and "path" in api_obj:
        detail["path"] = api_obj["path"]
    if api_obj.get("consumes"):
        detail["consumes"] = api_obj["consumes"]
    if api_obj.get("produces"):
        detail["produces"] = api_obj["produces"]

    # 安全认证
    security = api_obj.get("security", [])
    if security:
        detail["security"] = security

    # 操作类型
    sys_tags = api_obj.get("systemTags", {})
    op_type = sys_tags.get("operationType") or api_obj.get("operationType", "")
    if op_type:
        detail["operationType"] = op_type

    # 废弃
    if api_obj.get("deprecated"):
        detail["deprecated"] = True

    # 完整描述
    desc = api_obj.get("description", "")
    if desc:
        detail["description"] = clean_description(desc)

    # 补充说明
    for extra_key in ("requestParamsDescription", "responseParamsDescription", "extraInfo"):
        val = api_obj.get(extra_key, "")
        if val:
            detail[extra_key] = clean_description(val) if isinstance(val, str) else val

    # 完整参数
    parameters = api_obj.get("parameters", [])
    if parameters:
        detail["parameters"] = [_build_full_param(p) for p in parameters]

    # 完整响应
    responses = api_obj.get("responses", {})
    if responses:
        detail["responses"] = _build_full_responses(responses)

    # 错误码
    error_codes = api_obj.get("errorCodes", {})
    if error_codes:
        detail["errorCodes"] = error_codes

    # 响应示例
    response_demo = api_obj.get("responseDemo")
    if response_demo:
        if isinstance(response_demo, str):
            try:
                detail["responseDemo"] = json.loads(response_demo)
            except json.JSONDecodeError:
                detail["responseDemo"] = response_demo
        else:
            detail["responseDemo"] = response_demo

    return detail


def _build_full_param(param: dict) -> dict:
    """构建完整参数定义（清理无用字段）"""
    result: dict[str, Any] = {"name": param.get("name", ""), "in": param.get("in", "")}
    if "style" in param:
        result["style"] = param["style"]

    schema = param.get("schema", {})
    if isinstance(schema, dict):
        result["schema"] = clean_schema(schema)
    else:
        result["schema"] = schema
    return result


def _build_full_responses(responses: dict) -> dict:
    """构建完整响应定义"""
    result = {}
    for code, resp in responses.items():
        schema = resp.get("schema", {})
        if isinstance(schema, dict):
            result[code] = {"schema": clean_schema(schema)}
        else:
            result[code] = resp
    return result


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def split_product(
    source_path: Path,
    output_dir: Path,
    *,
    dry_run: bool = False,
) -> SplitStats:
    """拆分单个产品的 api-docs.json"""
    stats = SplitStats()

    # 加载源文件
    logger.info("加载源文件: %s", source_path)
    try:
        raw = source_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as e:
        stats.errors.append(f"源文件加载失败: {e}")
        return stats
    stats.source_bytes = len(raw.encode("utf-8"))

    info = data.get("info", {})
    product = info.get("product", source_path.stem)
    style = info.get("style", "unknown")
    apis = data.get("apis", {})

    if not apis:
        stats.errors.append(f"产品 {product} 没有 API 定义")
        return stats

    # $ref 解析器
    schemas = data.get("components", {}).get("schemas", {})
    resolver = RefResolver(schemas) if schemas else None

    # 产品输出目录
    product_dir = output_dir / product

    # === L0: index.json ===
    logger.info("生成 L0 index.json ...")
    index = build_index(data)
    l0_bytes = _write_json(product_dir / "index.json", index, dry_run=dry_run)
    stats.l0_bytes = l0_bytes
    stats.files_written += 1

    # === L1 + L2: 按 group 处理 ===
    directories = data.get("directories", [])
    groups_dir = product_dir / "groups"
    apis_dir = product_dir / "apis"

    # 构建 group → api_names 映射
    group_entries = []
    all_listed = set()

    for dir_entry in directories:
        if not isinstance(dir_entry, dict):
            continue
        title = dir_entry.get("title", "").strip()
        children = dir_entry.get("children", [])
        api_names = _flatten_children(children)
        slug = slugify(title)
        group_entries.append((slug, title, api_names))
        all_listed.update(api_names)

    # Orphan APIs
    orphans = [n for n in apis if n not in all_listed]
    if orphans:
        group_entries.append(("uncategorized", "未分类", orphans))

    for slug, title, api_names in group_entries:
        # L1: group file
        logger.info("  L1 group: %s (%d APIs)", slug, len(api_names))
        group_data = build_group(
            slug, title, api_names, apis,
            product=product, style=style, resolver=resolver,
        )
        l1_bytes = _write_json(groups_dir / f"{slug}.json", group_data, dry_run=dry_run)
        stats.l1_bytes += l1_bytes
        stats.files_written += 1
        stats.group_count += 1

        # L2: per-API files
        for api_name in api_names:
            api_obj = apis.get(api_name)
            if not api_obj or not isinstance(api_obj, dict):
                stats.warnings.append(f"API 对象缺失: {api_name}")
                continue

            if resolver:
                api_obj = resolver.resolve(api_obj)

            detail = build_api_detail(
                api_name, api_obj,
                product=product, style=style, group_slug=slug,
            )
            l2_bytes = _write_json(apis_dir / f"{api_name}.json", detail, dry_run=dry_run)
            stats.l2_bytes += l2_bytes
            stats.files_written += 1
            stats.api_count += 1

    logger.info(
        "拆分完成: %d groups, %d APIs, %d files",
        stats.group_count, stats.api_count, stats.files_written,
    )
    return stats


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_output(product_dir: Path, source_path: Path) -> list[str]:
    """验证输出完整性"""
    issues = []

    # 加载源文件获取预期 API 列表
    with open(source_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    expected_apis = set(data.get("apis", {}).keys())

    # 检查 index.json
    index_path = product_dir / "index.json"
    if not index_path.exists():
        issues.append("缺少 index.json")
        return issues

    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    # 检查所有 group 文件和 api 文件
    found_apis = set()
    for group in index.get("groups", []):
        slug = group["slug"]
        group_path = product_dir / "groups" / f"{slug}.json"
        if not group_path.exists():
            issues.append(f"缺少 group 文件: groups/{slug}.json")
            continue

        # 验证 JSON 合法性并从 group 文件中读取 API 列表
        try:
            with open(group_path, "r", encoding="utf-8") as f:
                group_data = json.load(f)
        except json.JSONDecodeError:
            issues.append(f"group 文件 JSON 格式错误: {slug}.json")
            continue

        for api_entry in group_data.get("apis", []):
            api_name = api_entry["name"]
            found_apis.add(api_name)
            api_path = product_dir / "apis" / f"{api_name}.json"
            if not api_path.exists():
                issues.append(f"缺少 API 文件: apis/{api_name}.json")
            else:
                try:
                    with open(api_path, "r", encoding="utf-8") as f:
                        json.load(f)
                except json.JSONDecodeError:
                    issues.append(f"API 文件 JSON 格式错误: {api_name}.json")

    # 检查覆盖率
    missing = expected_apis - found_apis
    if missing:
        issues.append(f"index 中缺少 {len(missing)} 个 API: {sorted(missing)[:10]}")

    extra = found_apis - expected_apis
    if extra:
        issues.append(f"index 中多出 {len(extra)} 个 API: {sorted(extra)[:10]}")

    return issues


# ---------------------------------------------------------------------------
# Batch Mode: 处理整个 api_metadata 目录
# ---------------------------------------------------------------------------


def split_batch(
    source_dir: Path,
    output_dir: Path,
    *,
    products_filter: set[str] | None = None,
    dry_run: bool = False,
    validate: bool = False,
) -> dict:
    """批量拆分 api_metadata 下的所有产品"""
    json_files = sorted(source_dir.rglob("*.json"))
    logger.info("发现 %d 个源文件", len(json_files))

    all_stats = SplitStats()
    catalog_entries = []

    for fpath in json_files:
        stem = fpath.stem
        if products_filter and stem not in products_filter:
            continue

        # 计算分类路径
        rel = fpath.relative_to(source_dir)
        category = str(rel.parent) if rel.parent != Path(".") else "Uncategorized"

        logger.info("处理: %s (分类: %s)", stem, category)
        stats = split_product(fpath, output_dir, dry_run=dry_run)

        # 合并统计
        all_stats.source_bytes += stats.source_bytes
        all_stats.api_count += stats.api_count
        all_stats.group_count += stats.group_count
        all_stats.files_written += stats.files_written
        all_stats.l0_bytes += stats.l0_bytes
        all_stats.l1_bytes += stats.l1_bytes
        all_stats.l2_bytes += stats.l2_bytes
        all_stats.errors.extend(stats.errors)
        all_stats.warnings.extend(stats.warnings)

        if not stats.errors:
            catalog_entries.append({
                "product": stem,
                "category": category,
                "apiCount": stats.api_count,
                "groupCount": stats.group_count,
                "index": f"{stem}/index.json",
            })

        # 验证
        if validate and not dry_run and not stats.errors:
            product_dir = output_dir / stem
            issues = validate_output(product_dir, fpath)
            if issues:
                for issue in issues:
                    all_stats.errors.append(f"[{stem}] 验证: {issue}")
                logger.warning("  验证发现 %d 个问题", len(issues))
            else:
                logger.info("  ✓ 验证通过")

    # 写入全局目录
    if catalog_entries:
        catalog = {
            "_version": VERSION,
            "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "productCount": len(catalog_entries),
            "products": catalog_entries,
        }
        _write_json(output_dir / "_catalog.json", catalog, dry_run=dry_run)
        all_stats.files_written += 1

    # 写入报告
    _write_json(output_dir / "_report.json", all_stats.summary(), dry_run=dry_run)
    all_stats.files_written += 1

    return all_stats.summary()


# ---------------------------------------------------------------------------
# I/O Helpers
# ---------------------------------------------------------------------------


def _write_json(path: Path, data: dict, *, dry_run: bool = False) -> int:
    """写入 JSON 文件，返回字节数"""
    content = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False)
    byte_count = len(content.encode("utf-8"))
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return byte_count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
    ))
    logger.setLevel(level)
    logger.addHandler(handler)


def main():
    parser = argparse.ArgumentParser(
        description="阿里云 API 元数据渐进披露拆分器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 拆分单个产品
  python splitter.py ../api_metadata/网络与CDN/专有网络/Vpc.json

  # 指定输出目录
  python splitter.py ../api_metadata/网络与CDN/专有网络/Vpc.json -o ../output_v2

  # 批量拆分整个目录
  python splitter.py ../api_metadata --batch -o ../output_v2

  # 批量拆分并验证
  python splitter.py ../api_metadata --batch --validate -o ../output_v2

  # 仅拆分指定产品
  python splitter.py ../api_metadata --batch --products Vpc,Ecs -o ../output_v2
        """,
    )
    parser.add_argument(
        "source", type=Path,
        help="源文件路径 (单个 .json) 或源目录 (配合 --batch)",
    )
    parser.add_argument(
        "-o", "--output-dir", type=Path, default=None,
        help="输出目录 (默认: 源文件同级的 output_v2/)",
    )
    parser.add_argument(
        "--batch", action="store_true",
        help="批量模式: source 为目录，递归处理所有 .json",
    )
    parser.add_argument(
        "--products", type=str, default=None,
        help="批量模式下仅处理指定产品 (逗号分隔)",
    )
    parser.add_argument(
        "--validate", action="store_true",
        help="拆分后验证输出完整性",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="模拟运行，不写入文件",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="详细日志",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {VERSION}",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    # 确定输出目录
    if args.output_dir:
        output_dir = args.output_dir
    elif args.batch:
        output_dir = args.source.parent / "output_v2"
    else:
        output_dir = args.source.parent / "output_v2"

    t0 = time.time()

    if args.batch:
        if not args.source.is_dir():
            logger.error("批量模式需要目录: %s", args.source)
            sys.exit(1)

        products_filter = None
        if args.products:
            products_filter = set(p.strip() for p in args.products.split(","))

        report = split_batch(
            args.source, output_dir,
            products_filter=products_filter,
            dry_run=args.dry_run,
            validate=args.validate,
        )
    else:
        if not args.source.is_file():
            logger.error("源文件不存在: %s", args.source)
            sys.exit(1)

        stats = split_product(args.source, output_dir, dry_run=args.dry_run)

        # 验证
        if args.validate and not args.dry_run and not stats.errors:
            product = json.loads(args.source.read_text())["info"]["product"]
            product_dir = output_dir / product
            issues = validate_output(product_dir, args.source)
            if issues:
                for issue in issues:
                    stats.errors.append(f"验证: {issue}")
            else:
                logger.info("✓ 验证通过")

        report = stats.summary()

    elapsed = time.time() - t0

    # 打印结果
    print("\n" + "=" * 60)
    print(f"  拆分完成 ({elapsed:.1f}s)")
    print("=" * 60)
    print(f"  API 数量:    {report['api_count']}")
    print(f"  分组数量:    {report['group_count']}")
    print(f"  生成文件:    {report['files_written']}")
    print(f"  源文件大小:  {report['source_bytes'] / 1024:.0f} KB")
    print(f"  输出总大小:  {report['output_bytes'] / 1024:.0f} KB ({report['ratio']})")
    lb = report["layer_bytes"]
    print(f"    L0 index:  {lb['L0_index'] / 1024:.1f} KB")
    print(f"    L1 groups: {lb['L1_groups'] / 1024:.1f} KB")
    print(f"    L2 apis:   {lb['L2_apis'] / 1024:.1f} KB")
    if report["source_bytes"] > 0:
        l0_pct = lb["L0_index"] / report["source_bytes"] * 100
        l01_pct = (lb["L0_index"] + lb["L1_groups"]) / report["source_bytes"] * 100
        print(f"  仅 L0 占源文件:     {l0_pct:.1f}%")
        print(f"  L0 + L1 占源文件:   {l01_pct:.1f}%")
    if report.get("errors"):
        print(f"\n  ⚠ 错误 ({len(report['errors'])}):")
        for e in report["errors"][:10]:
            print(f"    - {e}")
    if report.get("warnings"):
        print(f"\n  ⚡ 警告 ({len(report['warnings'])}):")
        for w in report["warnings"][:10]:
            print(f"    - {w}")

    sys.exit(1 if report.get("errors") else 0)


if __name__ == "__main__":
    main()
