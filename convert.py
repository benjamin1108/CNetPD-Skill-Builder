#!/usr/bin/env python3
"""
阿里云 API 元数据分层转换器 (Progressive Disclosure Converter)

将阿里云 OpenAPI 元数据的单体 JSON 文件转换为四层渐进披露结构：
  L0 - Product Index    (产品索引，~500B)
  L1 - API Overview     (API 概览，~2KB/个)
  L2 - API Detail       (API 详情，~5KB/个)
  L3 - Error & Demo     (错误码和示例，~3KB/个)

同时生成 _catalog.json 全局目录索引。

支持全部 API 风格：RPC / ROA / V3 / FC / OSS / PDS / AliGenie
支持 $ref 引用解析（components.schemas）

用法:
  python convert.py <source_dir> <output_dir> [options]

示例:
  python convert.py ./api_metadata ./api_layered
  python convert.py ./api_metadata ./api_layered --products VpcPeer,Ecs
  python convert.py ./api_metadata ./api_layered --dry-run
  python convert.py ./api_metadata ./api_layered --validate
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VERSION = "1.0.0"

# API 字段分类 - 每层保留哪些字段
L1_PARAM_SCHEMA_KEYS = {"type", "format", "required", "enum", "enumValueTitles", "default"}
L2_PARAM_SCHEMA_STRIP_KEYS = {"title", "docRequired", "isFileTransferUrl", "readOnly"}
L3_ONLY_KEYS = {"errorCodes", "responseDemo"}

# systemTags 中对 PRD 无意义的字段
SYSTEM_TAGS_STRIP_KEYS = {
    "abilityTreeCode", "abilityTreeNodes",
    "autoTest", "notSupportAutoTestReason",
    "tenantRelevance",
}

# 通用辅助参数（DryRun / ClientToken 等）在 L1 中简化处理
COMMON_AUXILIARY_PARAMS = {"DryRun", "ClientToken"}
PRIVATE_KEY_PEM_RE = re.compile(
    r"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----.*?-----END(?: [A-Z0-9]+)? PRIVATE KEY-----",
    re.DOTALL,
)
SENSITIVE_EXAMPLE_FIELDS = {
    "privatekey",
    "privatekeybody",
    "clientkey",
    "customdomainprivatekey",
}

logger = logging.getLogger("api_converter")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ConvertStats:
    """转换统计信息"""
    products_processed: int = 0
    products_skipped: int = 0
    apis_processed: int = 0
    files_written: int = 0
    total_source_bytes: int = 0
    total_output_bytes: int = 0
    l0_bytes: int = 0
    l1_bytes: int = 0
    l2_bytes: int = 0
    l3_bytes: int = 0
    catalog_bytes: int = 0
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def compression_ratio(self) -> float:
        if self.total_source_bytes == 0:
            return 0
        return 1 - self.total_output_bytes / self.total_source_bytes

    def to_dict(self) -> dict:
        return {
            "version": VERSION,
            "products_processed": self.products_processed,
            "products_skipped": self.products_skipped,
            "apis_processed": self.apis_processed,
            "files_written": self.files_written,
            "total_source_bytes": self.total_source_bytes,
            "total_output_bytes": self.total_output_bytes,
            "layer_bytes": {
                "L0": self.l0_bytes,
                "L1": self.l1_bytes,
                "L2": self.l2_bytes,
                "L3": self.l3_bytes,
                "catalog": self.catalog_bytes,
            },
            "compression_ratio": f"{self.compression_ratio:.1%}",
            "errors_count": len(self.errors),
            "warnings_count": len(self.warnings),
            "errors": self.errors[:50],
            "warnings": self.warnings[:50],
        }


# ---------------------------------------------------------------------------
# Ref resolver
# ---------------------------------------------------------------------------


class RefResolver:
    """解析 $ref 引用，将 components.schemas 中的定义内联展开。"""

    def __init__(self, schemas: dict[str, Any]):
        self._schemas = schemas
        self._resolved_cache: dict[str, Any] = {}
        self._resolving: set[str] = set()  # 防止循环引用

    def resolve(self, obj: Any, max_depth: int = 10) -> Any:
        """递归解析对象中的所有 $ref 引用"""
        if max_depth <= 0:
            return obj
        if isinstance(obj, dict):
            if "$ref" in obj:
                return self._resolve_ref(obj["$ref"], max_depth - 1)
            return {k: self.resolve(v, max_depth) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.resolve(item, max_depth) for item in obj]
        return obj

    def _resolve_ref(self, ref_path: str, max_depth: int) -> Any:
        """解析单个 $ref 路径，如 '#/components/schemas/Foo'"""
        if ref_path in self._resolved_cache:
            return copy.deepcopy(self._resolved_cache[ref_path])

        # 防止循环引用
        if ref_path in self._resolving:
            logger.warning("检测到循环引用: %s, 保留原始 $ref", ref_path)
            return {"$ref": ref_path, "_circular": True}

        # 解析路径
        parts = ref_path.lstrip("#/").split("/")
        if len(parts) >= 3 and parts[0] == "components" and parts[1] == "schemas":
            schema_name = "/".join(parts[2:])
            if schema_name in self._schemas:
                self._resolving.add(ref_path)
                resolved = self.resolve(
                    copy.deepcopy(self._schemas[schema_name]), max_depth
                )
                self._resolving.discard(ref_path)
                self._resolved_cache[ref_path] = resolved
                return copy.deepcopy(resolved)

        # 无法解析，保留原样
        logger.debug("无法解析 $ref: %s", ref_path)
        return {"$ref": ref_path, "_unresolved": True}


# ---------------------------------------------------------------------------
# Parameter processing
# ---------------------------------------------------------------------------


def extract_constraints(schema: dict) -> dict[str, Any] | None:
    """从 schema 中提取约束条件为紧凑字符串或字典"""
    constraints = {}
    constraint_keys = {
        "maximum", "minimum", "exclusiveMaximum", "exclusiveMinimum",
        "maxLength", "minLength", "maxItems", "minItems", "pattern",
    }
    for k in constraint_keys:
        if k in schema:
            constraints[k] = schema[k]
    return constraints or None


def extract_note(schema: dict, param_name: str) -> str | None:
    """从 description 中提取简短注释（一句话）"""
    desc = schema.get("description", "")
    if not desc:
        return None

    # 对于常见辅助参数，给固定简短注释
    if param_name == "DryRun":
        return "预检请求，默认false"
    if param_name == "ClientToken":
        return "幂等性Token"

    # 提取第一句作为 note
    # 去掉 markdown 链接标记 [text](~~id~~)
    clean = re.sub(r"\[([^\]]+)\]\(~~\d+~~\)", r"\1", desc)
    clean = re.sub(r"\(~~\d+~~\)", "", clean)
    # 取第一个句号或换行前的内容
    first_line = clean.split("\n")[0].strip()
    # 截断到合理长度
    if len(first_line) > 80:
        first_line = first_line[:77] + "..."
    return first_line or None


def _is_deprecated_description(desc: str) -> bool:
    """检测 description 是否标记了字段已废弃"""
    if not desc:
        return False
    # 常见废弃标记模式
    patterns = [
        r"该字段已废弃",
        r"该参数已废弃",
        r"\*\*该字段已废弃\*\*",
        r"\*\*该参数已废弃\*\*",
        r"^\s*\[?deprecated\]?",
    ]
    for pat in patterns:
        if re.search(pat, desc[:60], re.IGNORECASE):
            return True
    return False


def sanitize_sensitive_example(value: Any, *, field_name: str | None = None) -> Any:
    """清洗示例中的私钥内容，避免把 PEM 或私钥样例写入产物。"""
    if isinstance(value, str):
        cleaned = PRIVATE_KEY_PEM_RE.sub("[REDACTED PRIVATE KEY]", value)
        if cleaned != value:
            return cleaned
        if field_name and field_name.lower() in SENSITIVE_EXAMPLE_FIELDS and value.strip():
            return "[REDACTED SENSITIVE EXAMPLE]"
        return value
    if isinstance(value, list):
        return [sanitize_sensitive_example(item, field_name=field_name) for item in value]
    if isinstance(value, dict):
        return {
            k: sanitize_sensitive_example(v, field_name=k) for k, v in value.items()
        }
    return value


def _build_l1_opt_entry(
    name: str, schema: dict, param_format: str | None = None
) -> dict[str, Any] | None:
    """为单个非必填参数构建 L1 摘要条目。返回 None 表示应跳过（如已废弃字段）"""
    # 检测废弃字段：description 以 "该字段已废弃" / "该参数已废弃" 开头
    desc = schema.get("description", "")
    if schema.get("deprecated") or _is_deprecated_description(desc):
        return None  # L1 层跳过废弃字段，L2 仍保留完整信息

    param_type = schema.get("type", "string")
    opt: dict[str, Any] = {"name": name, "type": param_type}
    if param_format or schema.get("format"):
        opt["format"] = param_format or schema.get("format")

    # 枚举值
    enum_titles = schema.get("enumValueTitles")
    enum_vals = schema.get("enum")
    if enum_titles:
        opt["enum"] = list(enum_titles.keys())
    elif enum_vals:
        opt["enum"] = enum_vals

    # 默认值
    default = schema.get("default")
    if default is not None:
        opt["default"] = default

    # 简短注释
    note = extract_note(schema, name)
    if note:
        opt["note"] = note

    # 嵌套结构的 items 类型提示
    if param_type == "array":
        items = schema.get("items", {})
        if isinstance(items, dict):
            items_type = items.get("type", "string")
            if items_type == "object":
                props = items.get("properties", {})
                opt["itemFields"] = list(props.keys())
            else:
                opt["itemType"] = items_type

    # 约束
    constraints = extract_constraints(schema)
    if constraints:
        opt["constraints"] = constraints

    return opt


def _extract_body_params(
    schema: dict,
) -> tuple[list[str], list[dict]]:
    """从 ROA body 参数的 schema 中提取 required/optional 字段列表"""
    required = []
    optional = []
    properties = schema.get("properties", {})

    for field_name, field_schema in properties.items():
        if not isinstance(field_schema, dict):
            continue
        is_req = field_schema.get("required", False)
        if isinstance(is_req, str):
            is_req = is_req.lower() == "true"

        if is_req:
            required.append(field_name)
        else:
            opt = _build_l1_opt_entry(field_name, field_schema)
            if opt is not None:
                optional.append(opt)

    return required, optional


def build_l1_params(
    parameters: list[dict], *, is_roa: bool = False
) -> tuple[list[str], list[dict]]:
    """构建 L1 层的参数摘要。返回 (required_params, optional_params)"""
    required_params = []
    optional_params = []

    for param in parameters:
        name = param.get("name", "")
        schema = param.get("schema", {})
        if isinstance(schema, str):
            # 极少数情况 schema 可能是字符串
            continue

        in_location = param.get("in", "")

        # ROA body 参数：展开其内部字段
        if in_location == "body" and schema.get("type") == "object":
            body_props = schema.get("properties", {})
            if body_props:
                body_req, body_opt = _extract_body_params(schema)
                required_params.extend(body_req)
                optional_params.extend(body_opt)
                continue

        # 判断是否必填
        is_required = schema.get("required", False)
        if isinstance(is_required, str):
            is_required = is_required.lower() == "true"

        param_type = schema.get("type", "string")
        param_format = schema.get("format")

        if is_required:
            required_params.append(name)
        else:
            opt = _build_l1_opt_entry(name, schema, param_format)
            if opt is not None:
                optional_params.append(opt)

    return required_params, optional_params


def build_l1_returns(responses: dict) -> list[str]:
    """提取返回字段名列表"""
    fields = []
    for status_code, resp in responses.items():
        schema = resp.get("schema", {})
        if isinstance(schema, dict):
            props = schema.get("properties", {})
            fields.extend(props.keys())
    return fields


def categorize_errors(error_codes: dict) -> dict:
    """将错误码按类别聚合"""
    categories: dict[str, list[str]] = defaultdict(list)
    total = 0

    for status_code, errors in error_codes.items():
        if not isinstance(errors, list):
            continue
        for err in errors:
            code = err.get("errorCode", "")
            total += 1
            # 提取错误码前缀作为分类
            # e.g. "ResourceNotFound.InstanceId" -> "ResourceNotFound"
            # e.g. "IncorrectStatus.VpcPeer" -> "IncorrectStatus"
            # e.g. "QuotaExceeded.VpcPeerCountPerVpc" -> "QuotaExceeded"
            prefix = code.split(".")[0] if "." in code else code
            # 进一步合并常见前缀
            category = _normalize_error_category(prefix)
            categories[category].append(code)

    if not categories:
        return {}

    summary = {
        "count": total,
        "categories": {},
    }
    for cat, codes in sorted(categories.items()):
        summary["categories"][cat] = {
            "count": len(codes),
            "codes": codes,
        }

    return summary


def _normalize_error_category(prefix: str) -> str:
    """将错误码前缀归一化为语义类别"""
    mapping = {
        "ResourceNotFound": "资源不存在",
        "IncorrectStatus": "状态不正确",
        "IncorrectBusinessStatus": "商业状态不正确",
        "ResourceAlreadyExist": "资源已存在",
        "QuotaExceeded": "配额超限",
        "OperationFailed": "操作失败",
        "OperationDenied": "操作被拒绝",
        "UnsupportedRegion": "地域不支持",
        "Forbidden": "权限不足",
        "InvalidParam": "参数无效",
        "IllegalParam": "参数非法",
        "InvalidInstanceIds": "实例ID无效",
        "InvalidInstanceType": "实例类型无效",
        "InvalidTagKey": "标签键无效",
        "NumberExceed": "数量超限",
        "BothEmpty": "参数不能同时为空",
        "MissingParameter": "缺少参数",
    }
    return mapping.get(prefix, prefix)


# ---------------------------------------------------------------------------
# L2 parameter building
# ---------------------------------------------------------------------------


def build_l2_param(param: dict) -> dict:
    """构建 L2 层的完整参数定义（去掉无用字段）"""
    result: dict[str, Any] = {
        "name": param.get("name", ""),
        "in": param.get("in", ""),
    }

    if "style" in param:
        result["style"] = param["style"]

    schema = param.get("schema", {})
    if not isinstance(schema, dict):
        result["schema"] = schema
        return result

    # 构建精简后的 schema
    clean_schema: dict[str, Any] = {}

    for k, v in schema.items():
        if k in L2_PARAM_SCHEMA_STRIP_KEYS:
            continue
        clean_schema[k] = v

    # 清理 description 中的内部链接标记
    if "description" in clean_schema:
        clean_schema["description"] = _clean_description(clean_schema["description"])

    # 递归处理嵌套结构
    if "example" in clean_schema:
        clean_schema["example"] = sanitize_sensitive_example(
            clean_schema["example"], field_name=param.get("name", "")
        )
    if "items" in clean_schema and isinstance(clean_schema["items"], dict):
        clean_schema["items"] = _clean_schema_recursive(
            clean_schema["items"], field_name=param.get("name", "")
        )
    if "properties" in clean_schema and isinstance(clean_schema["properties"], dict):
        clean_schema["properties"] = {
            k: _clean_schema_recursive(v, field_name=k)
            for k, v in clean_schema["properties"].items()
        }

    result["schema"] = clean_schema
    return result


def _clean_schema_recursive(
    schema: dict, *, field_name: str | None = None
) -> dict:
    """递归清理 schema 中的无用字段"""
    if not isinstance(schema, dict):
        return schema

    result = {}
    for k, v in schema.items():
        if k in L2_PARAM_SCHEMA_STRIP_KEYS:
            continue
        if k == "description" and isinstance(v, str):
            result[k] = _clean_description(v)
        elif k == "example":
            result[k] = sanitize_sensitive_example(v, field_name=field_name)
        elif k == "items" and isinstance(v, dict):
            result[k] = _clean_schema_recursive(v, field_name=field_name)
        elif k == "properties" and isinstance(v, dict):
            result[k] = {
                pk: _clean_schema_recursive(pv, field_name=pk) for pk, pv in v.items()
            }
        else:
            result[k] = v
    return result


def _clean_description(desc: str) -> str:
    """清理 description 中的内部文档链接标记"""
    if not desc:
        return desc
    # 去掉 [text](~~12345~~) -> text
    cleaned = re.sub(r"\[([^\]]*)\]\(~~\d+~~\)", r"\1", desc)
    # 去掉裸的 (~~12345~~)
    cleaned = re.sub(r"\(~~\d+~~\)", "", cleaned)
    # 去掉 <props="china">...</props> 和 <props="intl">...</props> 标记
    cleaned = re.sub(r'<props="[^"]*">(.*?)</props>', r"\1", cleaned, flags=re.DOTALL)
    return cleaned.strip()


def build_l2_responses(responses: dict) -> dict:
    """构建 L2 层的响应定义"""
    result = {}
    for status_code, resp in responses.items():
        schema = resp.get("schema", {})
        if isinstance(schema, dict):
            clean = _clean_schema_recursive(schema)
            result[status_code] = {"schema": clean}
        else:
            result[status_code] = resp
    return result


# ---------------------------------------------------------------------------
# Directory flattening
# ---------------------------------------------------------------------------


def flatten_directories(directories: list) -> list[str]:
    """
    将嵌套的 directories 结构展平为 API 名称列表。

    directories 可能包含：
      - 字符串（直接是 API 名称）
      - 字典（分组目录，含 children 字段，children 可递归嵌套）
    """
    result: list[str] = []
    for item in directories:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            children = item.get("children", [])
            result.extend(flatten_directories(children))
    return result


# ---------------------------------------------------------------------------
# Layer builders
# ---------------------------------------------------------------------------


def build_l0(
    data: dict, *, source_path: str, rel_category: str
) -> dict:
    """构建 L0 - Product Index"""
    info = data.get("info", {})
    product = info.get("product", "unknown")
    style = info.get("style", "unknown")
    api_version = info.get("version", "")
    directories = data.get("directories", [])

    apis_summary = []
    apis = data.get("apis", {})

    # 优先按 directories 顺序，展平嵌套目录
    api_names = flatten_directories(directories) if directories else list(apis.keys())

    for api_name in api_names:
        api_obj = apis.get(api_name)
        if not api_obj or not isinstance(api_obj, dict):
            continue

        entry: dict[str, Any] = {
            "name": api_name,
            "title": api_obj.get("title", ""),
        }

        # ROA 风格需要保留 path
        if style == "ROA" and "path" in api_obj:
            entry["method"] = (api_obj.get("methods") or [""])[0].upper()
            entry["path"] = api_obj["path"]

        # 标记废弃
        if api_obj.get("deprecated"):
            entry["deprecated"] = True

        apis_summary.append(entry)

    l0: dict[str, Any] = {
        "_layer": "L0",
        "_version": VERSION,
        "product": product,
        "apiVersion": api_version,
        "style": style,
        "category": rel_category,
        "apiCount": len(apis_summary),
        "apis": apis_summary,
    }

    # 区域摘要（去重）
    endpoints = data.get("endpoints", [])
    if endpoints:
        regions = sorted(set(ep.get("regionId", "") for ep in endpoints))
        unique_endpoints = sorted(set(ep.get("endpoint", "") for ep in endpoints))
        l0["regions"] = regions
        l0["endpoints"] = unique_endpoints

    return l0


def build_l1(
    api_name: str, api_obj: dict, *, product: str, style: str
) -> dict:
    """构建 L1 - API Overview"""
    is_roa = style in ("ROA", "V3")

    l1: dict[str, Any] = {
        "_layer": "L1",
        "product": product,
        "api": api_name,
        "title": api_obj.get("title", ""),
        "summary": api_obj.get("summary", ""),
    }

    # ROA 路径信息
    if is_roa and "path" in api_obj:
        l1["method"] = (api_obj.get("methods") or [""])[0].upper()
        l1["path"] = api_obj["path"]

    # 操作类型 - 优先用 systemTags 中的
    sys_tags = api_obj.get("systemTags", {})
    op_type = sys_tags.get("operationType") or api_obj.get("operationType", "")
    if op_type:
        l1["operationType"] = op_type

    # 计费类型（仅当不是 free 时才保留）
    charge_type = sys_tags.get("chargeType", "free")
    if charge_type != "free":
        l1["chargeType"] = charge_type

    # 废弃标记
    if api_obj.get("deprecated"):
        l1["deprecated"] = True

    # 参数摘要
    parameters = api_obj.get("parameters", [])
    required_params, optional_params = build_l1_params(parameters, is_roa=is_roa)
    l1["requiredParams"] = required_params
    if optional_params:
        l1["optionalParams"] = optional_params

    # 返回字段
    responses = api_obj.get("responses", {})
    returns = build_l1_returns(responses)
    if returns:
        l1["returns"] = returns

    # 错误摘要
    error_codes = api_obj.get("errorCodes", {})
    if error_codes:
        error_summary = categorize_errors(error_codes)
        if error_summary:
            l1["errorSummary"] = error_summary

    return l1


def build_l2(
    api_name: str, api_obj: dict, *, product: str, style: str
) -> dict:
    """构建 L2 - API Detail"""
    is_roa = style in ("ROA", "V3")

    l2: dict[str, Any] = {
        "_layer": "L2",
        "product": product,
        "api": api_name,
    }

    # 协议信息（L2 才需要）
    if api_obj.get("methods"):
        l2["methods"] = api_obj["methods"]
    if is_roa and "path" in api_obj:
        l2["path"] = api_obj["path"]
    if api_obj.get("consumes"):
        l2["consumes"] = api_obj["consumes"]
    if api_obj.get("produces"):
        l2["produces"] = api_obj["produces"]

    # 完整描述（清理后）
    desc = api_obj.get("description", "")
    if desc:
        l2["description"] = _clean_description(desc)

    # 完整参数
    parameters = api_obj.get("parameters", [])
    l2["parameters"] = [build_l2_param(p) for p in parameters]

    # 完整响应
    responses = api_obj.get("responses", {})
    l2["responses"] = build_l2_responses(responses)

    return l2


def build_l3(
    api_name: str, api_obj: dict, *, product: str
) -> dict | None:
    """构建 L3 - Error Codes & Demos"""
    error_codes = api_obj.get("errorCodes", {})
    response_demo = api_obj.get("responseDemo", "")

    # 如果既没有错误码也没有示例，跳过 L3
    if not error_codes and not response_demo:
        return None

    l3: dict[str, Any] = {
        "_layer": "L3",
        "product": product,
        "api": api_name,
    }

    if error_codes:
        l3["errorCodes"] = error_codes

    if response_demo:
        # 尝试解析 responseDemo（通常是 JSON 字符串）
        if isinstance(response_demo, str):
            try:
                parsed = json.loads(response_demo)
                l3["responseDemo"] = sanitize_sensitive_example(parsed)
            except json.JSONDecodeError:
                l3["responseDemo"] = sanitize_sensitive_example(response_demo)
        else:
            l3["responseDemo"] = sanitize_sensitive_example(response_demo)

    return l3


# ---------------------------------------------------------------------------
# Catalog builder
# ---------------------------------------------------------------------------


def build_catalog(
    products: list[dict], *, output_dir: Path
) -> dict:
    """构建全局目录 _catalog.json"""
    categories: dict[str, list[dict]] = defaultdict(list)

    for p in products:
        cat = p["category"]
        categories[cat].append({
            "product": p["product"],
            "apiVersion": p["apiVersion"],
            "style": p["style"],
            "apiCount": p["apiCount"],
            "l0": p["l0_path"],
        })

    catalog = {
        "_layer": "catalog",
        "_version": VERSION,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "productCount": len(products),
        "categoryCount": len(categories),
        "categories": dict(sorted(categories.items())),
    }

    return catalog


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------


def write_json(
    path: Path, data: dict, *, dry_run: bool = False, compact: bool = False
) -> int:
    """写入 JSON 文件，返回写入字节数。compact=True 时使用紧凑格式"""
    if compact:
        content = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
    else:
        content = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False)
    byte_count = len(content.encode("utf-8"))

    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    return byte_count


def safe_filename(name: str) -> str:
    """将名称转为安全的文件名"""
    # 保留字母数字下划线和短横线
    return re.sub(r"[^\w\-]", "_", name)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_output(output_dir: Path) -> list[str]:
    """验证输出目录结构完整性"""
    issues = []

    catalog_path = output_dir / "_catalog.json"
    if not catalog_path.exists():
        issues.append("缺少 _catalog.json")
        return issues

    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    for cat, products in catalog.get("categories", {}).items():
        for prod_info in products:
            l0_path = output_dir / prod_info["l0"]
            if not l0_path.exists():
                issues.append(f"缺少 L0 文件: {prod_info['l0']}")
                continue

            with open(l0_path, "r", encoding="utf-8") as f:
                l0 = json.load(f)

            product_dir = l0_path.parent
            for api_entry in l0.get("apis", []):
                api_name = api_entry["name"]
                safe_name = safe_filename(api_name)

                l1_path = product_dir / "L1" / f"{safe_name}.json"
                l2_path = product_dir / "L2" / f"{safe_name}.json"

                if not l1_path.exists():
                    issues.append(f"缺少 L1: {l1_path.relative_to(output_dir)}")
                if not l2_path.exists():
                    issues.append(f"缺少 L2: {l2_path.relative_to(output_dir)}")

                # L3 是可选的，不做强制检查
                # 但如果存在应该是合法 JSON
                l3_path = product_dir / "L3" / f"{safe_name}.json"
                if l3_path.exists():
                    try:
                        with open(l3_path, "r", encoding="utf-8") as f:
                            json.load(f)
                    except json.JSONDecodeError:
                        issues.append(f"L3 JSON 格式错误: {l3_path.relative_to(output_dir)}")

    return issues


# ---------------------------------------------------------------------------
# Main conversion
# ---------------------------------------------------------------------------


def convert_product(
    source_path: Path,
    output_dir: Path,
    *,
    rel_category: str,
    stats: ConvertStats,
    dry_run: bool = False,
    compact_l3: bool = True,
) -> dict | None:
    """转换单个产品 JSON 文件"""
    try:
        with open(source_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        stats.errors.append(f"JSON 解析失败: {source_path}: {e}")
        stats.products_skipped += 1
        return None

    stats.total_source_bytes += source_path.stat().st_size

    info = data.get("info", {})
    product = info.get("product", source_path.stem)
    style = info.get("style", "unknown")
    api_version = info.get("version", "")
    apis = data.get("apis", {})

    if not apis:
        stats.warnings.append(f"产品 {product} 没有 API 定义，跳过")
        stats.products_skipped += 1
        return None

    # 解析 $ref 引用
    schemas = data.get("components", {}).get("schemas", {})
    resolver = RefResolver(schemas) if schemas else None

    # 产品输出目录
    product_dir = output_dir / rel_category / safe_filename(product)

    # === L0 ===
    l0 = build_l0(data, source_path=str(source_path), rel_category=rel_category)
    l0_path = product_dir / "L0.json"
    l0_bytes = write_json(l0_path, l0, dry_run=dry_run)
    stats.l0_bytes += l0_bytes
    stats.files_written += 1

    # === 逐 API 处理 ===
    directories = data.get("directories", [])
    api_names = flatten_directories(directories) if directories else list(apis.keys())

    for api_name in api_names:
        api_obj = apis.get(api_name)
        if not api_obj or not isinstance(api_obj, dict):
            stats.warnings.append(f"{product}/{api_name}: API 对象缺失或无效")
            continue

        # 如果有 $ref，先解析
        if resolver:
            api_obj = resolver.resolve(api_obj)

        safe_name = safe_filename(api_name)

        # L1
        l1 = build_l1(api_name, api_obj, product=product, style=style)
        l1_bytes = write_json(
            product_dir / "L1" / f"{safe_name}.json", l1, dry_run=dry_run
        )
        stats.l1_bytes += l1_bytes
        stats.files_written += 1

        # L2
        l2 = build_l2(api_name, api_obj, product=product, style=style)
        l2_bytes = write_json(
            product_dir / "L2" / f"{safe_name}.json", l2, dry_run=dry_run
        )
        stats.l2_bytes += l2_bytes
        stats.files_written += 1

        # L3 (optional)
        l3 = build_l3(api_name, api_obj, product=product)
        if l3:
            l3_bytes = write_json(
                product_dir / "L3" / f"{safe_name}.json", l3,
                dry_run=dry_run, compact=compact_l3,
            )
            stats.l3_bytes += l3_bytes
            stats.files_written += 1

        stats.apis_processed += 1

    stats.products_processed += 1
    logger.info(
        "✓ %s (%s, %d APIs, style=%s)",
        product, rel_category, len(api_names), style,
    )

    return {
        "product": product,
        "apiVersion": api_version,
        "style": style,
        "category": rel_category,
        "apiCount": len(api_names),
        "l0_path": str((product_dir / "L0.json").relative_to(output_dir)),
    }


def convert_all(
    source_dir: Path,
    output_dir: Path,
    *,
    products_filter: set[str] | None = None,
    dry_run: bool = False,
    validate: bool = False,
    compact_l3: bool = True,
) -> ConvertStats:
    """转换全部产品"""
    stats = ConvertStats()
    product_entries = []

    # 遍历所有 JSON 文件
    json_files = sorted(source_dir.rglob("*.json"))
    total = len(json_files)

    logger.info("发现 %d 个源文件", total)

    for i, json_path in enumerate(json_files, 1):
        # 计算相对分类路径
        rel = json_path.relative_to(source_dir)
        # 分类 = 父目录路径（去掉文件名）
        rel_category = str(rel.parent) if rel.parent != Path(".") else "Uncategorized"

        # 过滤产品
        if products_filter:
            stem = json_path.stem
            if stem not in products_filter:
                continue

        logger.debug("[%d/%d] 处理 %s", i, total, rel)

        result = convert_product(
            json_path, output_dir,
            rel_category=rel_category,
            stats=stats,
            dry_run=dry_run,
            compact_l3=compact_l3,
        )

        if result:
            product_entries.append(result)

    # === 全局目录 ===
    if product_entries:
        catalog = build_catalog(product_entries, output_dir=output_dir)
        catalog_path = output_dir / "_catalog.json"
        catalog_bytes = write_json(catalog_path, catalog, dry_run=dry_run)
        stats.catalog_bytes = catalog_bytes
        stats.files_written += 1

    stats.total_output_bytes = (
        stats.l0_bytes + stats.l1_bytes + stats.l2_bytes
        + stats.l3_bytes + stats.catalog_bytes
    )

    # === 验证 ===
    if validate and not dry_run:
        issues = validate_output(output_dir)
        if issues:
            for issue in issues:
                stats.errors.append(f"验证失败: {issue}")
            logger.warning("验证发现 %d 个问题", len(issues))
        else:
            logger.info("✓ 验证通过")

    # === 写入统计报告 ===
    report_path = output_dir / "_report.json"
    write_json(report_path, stats.to_dict(), dry_run=dry_run)
    stats.files_written += 1

    return stats


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
        description="阿里云 API 元数据分层转换器 (Progressive Disclosure Converter)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s ./api_metadata ./api_layered
  %(prog)s ./api_metadata ./api_layered --products VpcPeer,Ecs
  %(prog)s ./api_metadata ./api_layered --dry-run
  %(prog)s ./api_metadata ./api_layered --validate
        """,
    )
    parser.add_argument("source_dir", type=Path, help="源元数据目录")
    parser.add_argument("output_dir", type=Path, help="输出目录")
    parser.add_argument(
        "--products", type=str, default=None,
        help="仅处理指定产品（逗号分隔），如: VpcPeer,Ecs",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="模拟运行，不写入文件",
    )
    parser.add_argument(
        "--validate", action="store_true",
        help="转换后验证输出完整性",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="详细日志输出",
    )
    parser.add_argument(
        "--no-compact", action="store_true",
        help="L3 文件也使用格式化输出（默认紧凑格式）",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {VERSION}",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if not args.source_dir.is_dir():
        logger.error("源目录不存在: %s", args.source_dir)
        sys.exit(1)

    products_filter = None
    if args.products:
        products_filter = set(p.strip() for p in args.products.split(","))
        logger.info("仅处理产品: %s", products_filter)

    logger.info("源目录: %s", args.source_dir)
    logger.info("输出目录: %s", args.output_dir)
    if args.dry_run:
        logger.info("** DRY RUN 模式 **")

    t0 = time.time()
    stats = convert_all(
        args.source_dir, args.output_dir,
        products_filter=products_filter,
        dry_run=args.dry_run,
        validate=args.validate,
        compact_l3=not args.no_compact,
    )
    elapsed = time.time() - t0

    # 输出汇总
    print("\n" + "=" * 60)
    print(f" 转换完成 ({elapsed:.1f}s)")
    print("=" * 60)
    print(f"  产品处理: {stats.products_processed}")
    print(f"  产品跳过: {stats.products_skipped}")
    print(f"  API 处理: {stats.apis_processed}")
    print(f"  文件生成: {stats.files_written}")
    print(f"  源文件大小: {stats.total_source_bytes / 1024 / 1024:.1f} MB")
    print(f"  输出大小:   {stats.total_output_bytes / 1024 / 1024:.1f} MB")
    print(f"    L0: {stats.l0_bytes / 1024:.0f} KB")
    print(f"    L1: {stats.l1_bytes / 1024:.0f} KB")
    print(f"    L2: {stats.l2_bytes / 1024:.0f} KB")
    print(f"    L3: {stats.l3_bytes / 1024:.0f} KB")
    print(f"    Catalog: {stats.catalog_bytes / 1024:.0f} KB")
    if stats.total_source_bytes > 0:
        l0_ratio = stats.l0_bytes / stats.total_source_bytes * 100
        l0_l1_ratio = (stats.l0_bytes + stats.l1_bytes) / stats.total_source_bytes * 100
        print(f"  仅加载 L0 占源文件: {l0_ratio:.1f}%")
        print(f"  加载 L0+L1 占源文件: {l0_l1_ratio:.1f}%")
    if stats.errors:
        print(f"\n  ⚠ 错误: {len(stats.errors)}")
        for err in stats.errors[:10]:
            print(f"    - {err}")
    if stats.warnings:
        print(f"\n  ⚡ 警告: {len(stats.warnings)}")
        for warn in stats.warnings[:10]:
            print(f"    - {warn}")

    sys.exit(1 if stats.errors else 0)


if __name__ == "__main__":
    main()
