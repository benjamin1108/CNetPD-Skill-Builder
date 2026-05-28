#!/usr/bin/env python3
"""
阿里云 API skill 批量生成器（标准版）

把 splitter.py 产出的分层数据，按原 api_metadata 目录层级批量打包成
面向 AI PRD 设计的 skill 目录。

每个产品独立产出：
  <target>/<category>/aliyun-<slug>-api/
    SKILL.md                         — 自动填元数据 + 分区速查表（含语义列）
    scripts/query.py                 — 产品无关的查询工具（从模板拷贝）
    data/<Product>/                  — 从 splitter 输出拷贝
    references/capability-patterns.md — 自动推断的候选能力依赖图

自动化覆盖：
  1. 产品显示名：从首个含产品代号的分组标题提取（如 Vpc → "专有网络（VPC）"）
  2. 分区"核心产品能力"列：扫描分区内 API，提取资源+操作合成一句话
  3. capability-patterns.md：扫描全产品 apis/*.json，按"返回字段 → 输入参数"
     名称匹配推断候选依赖图
  4. 目录层级：读 splitter 的 _catalog.json，或提供 --api-meta 回退到原目录结构

用法:
  python build_skill.py <splitter_output_dir> --target <target_dir>
  python build_skill.py output/ --target skills/
  python build_skill.py output/ --target skills/ --api-meta api_metadata/
  python build_skill.py output/ --target skills/ --products Vpc,Ecs --force
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

VERSION = "2.0.0"
logger = logging.getLogger("build_skill")

SELF_DIR = Path(__file__).resolve().parent
DEFAULT_QUERY_TEMPLATE = SELF_DIR / "aliyun-vpc-api" / "scripts" / "query.py"


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@dataclass
class BuildStats:
    products_built: int = 0
    products_skipped: int = 0
    files_written: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 产品名 → slug
# ---------------------------------------------------------------------------


def product_to_slug(product: str) -> str:
    """Vpc→vpc, ECS→ecs, CloudFirewall→cloud-firewall, R-kvstore→r-kvstore"""
    s = re.sub(r"(?<!^)(?<![A-Z])([A-Z])", r"-\1", product)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", s)
    s = s.lower()
    s = re.sub(r"[^a-z0-9\-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "product"


# ---------------------------------------------------------------------------
# 产品显示名抽取
# ---------------------------------------------------------------------------


def extract_display_name(
    product: str, groups: list[dict], category: str = ""
) -> str:
    """
    抽取产品显示名。优先级：
      1. 分组标题中含产品代号的条目（如 Vpc → "专有网络（VPC）"）
      2. 分类路径的叶子目录名 + 产品代号（如 Ecs + "计算/云服务器" → "云服务器（ECS）"）
      3. 回退到产品代号本身
    """
    product_upper = product.upper()
    for g in groups:
        title = g.get("title", "").strip()
        if not title:
            continue
        if product_upper in title.upper():
            return title
        clean = re.sub(r"[（(][^）)]*[）)]", "", title)
        if product_upper in clean.upper():
            return title

    if category:
        leaf = category.split("/")[-1].strip()
        if leaf and leaf not in {"Uncategorized", "其他"}:
            # 若叶子名已含产品代号，直接用
            if product_upper in leaf.upper():
                return leaf
            return f"{leaf}（{product_upper}）"

    return product


# ---------------------------------------------------------------------------
# 分区能力语义合成（扫 group 文件内的 API 列表）
# ---------------------------------------------------------------------------


_VERBS_EN = [
    "Describe", "Associate", "Dissociate", "Disassociate",
    "Unassociate", "Allocate", "Release", "Attach", "Detach",
    "Revoke", "Approve", "Reject", "Cancel", "Apply", "Create",
    "Delete", "Modify", "Update", "Remove", "Enable", "Disable",
    "Start", "Stop", "Bind", "Unbind", "Grant", "Copy", "Move",
    "List", "Get", "Add", "Set", "Check", "Rollback", "Refresh",
    "Activate", "Deactivate", "Upgrade", "Downgrade", "Replace",
    "Register", "Unregister", "Install", "Uninstall", "Import", "Export",
    "Publish", "Unpublish", "Transfer", "Convert", "Synchronize",
]

_VERB_CN = {
    "Create": "创建", "Delete": "删除", "Modify": "修改", "Update": "更新",
    "Describe": "查询", "List": "列出", "Get": "获取",
    "Associate": "关联", "Dissociate": "解关联", "Disassociate": "解关联",
    "Unassociate": "解关联",
    "Attach": "挂载", "Detach": "卸载", "Add": "添加", "Remove": "移除",
    "Enable": "启用", "Disable": "禁用", "Start": "启动", "Stop": "停止",
    "Bind": "绑定", "Unbind": "解绑", "Grant": "授权", "Revoke": "撤销",
    "Allocate": "分配", "Release": "释放",
    "Apply": "申请", "Cancel": "取消", "Approve": "批准", "Reject": "拒绝",
    "Copy": "复制", "Move": "迁移", "Set": "设置", "Check": "检查",
    "Rollback": "回滚", "Refresh": "刷新",
    "Activate": "激活", "Deactivate": "停用",
    "Upgrade": "升级", "Downgrade": "降级", "Replace": "替换",
    "Register": "注册", "Unregister": "注销",
    "Install": "安装", "Uninstall": "卸载",
    "Import": "导入", "Export": "导出",
    "Publish": "发布", "Unpublish": "下架",
    "Transfer": "转移", "Convert": "转换", "Synchronize": "同步",
}

# CRUD 语义顺序，渲染时优先这个顺序
_VERB_ORDER = [
    "创建", "查询", "列出", "获取", "修改", "更新", "删除",
    "启用", "禁用", "启动", "停止", "激活", "停用",
    "关联", "解关联", "绑定", "解绑", "挂载", "卸载", "添加", "移除",
    "分配", "释放", "申请", "授权", "撤销",
    "批准", "拒绝", "取消",
]


def _split_verb_and_resource(api_name: str) -> tuple[str, str]:
    """Split API name into (verb, resource_noun) — 用最长前缀匹配"""
    for v in sorted(_VERBS_EN, key=len, reverse=True):
        if api_name.startswith(v) and (
            len(api_name) == len(v) or api_name[len(v)].isupper()
        ):
            return v, api_name[len(v):]
    return "", api_name


def synthesize_capability_desc(group_data: dict) -> str:
    """基于分组内 API 合成一句话能力描述"""
    apis = group_data.get("apis", [])
    if not apis:
        return "—"

    resources: list[str] = []
    seen_resources: set[str] = set()
    verbs_cn_set: set[str] = set()

    for api in apis:
        name = api.get("name", "")
        if api.get("deprecated"):
            continue
        verb, resource = _split_verb_and_resource(name)
        if verb in _VERB_CN:
            verbs_cn_set.add(_VERB_CN[verb])
        if resource and resource not in seen_resources:
            seen_resources.add(resource)
            resources.append(resource)

    # 取前 N 个资源（通常是该分区的主资源）
    top_resources = resources[:4]
    # 按 CRUD 顺序排序 verbs
    ordered_verbs = [v for v in _VERB_ORDER if v in verbs_cn_set]
    ordered_verbs.extend(v for v in verbs_cn_set if v not in ordered_verbs)

    if not top_resources and not ordered_verbs:
        return "—"

    res_str = "/".join(top_resources) if top_resources else ""
    verb_str = "/".join(ordered_verbs[:6])
    if res_str and verb_str:
        return f"{res_str}：{verb_str}"
    return res_str or verb_str


# ---------------------------------------------------------------------------
# 能力依赖图（扫所有 apis/*.json）
# ---------------------------------------------------------------------------


def _is_required(schema: dict) -> bool:
    val = schema.get("required", False)
    if isinstance(val, str):
        return val.lower() == "true"
    return bool(val)


def _extract_required_inputs(api: dict) -> list[str]:
    """抽取 API 的必填输入字段名"""
    fields: list[str] = []
    for p in api.get("parameters", []):
        if not isinstance(p, dict):
            continue
        schema = p.get("schema", {})
        if not isinstance(schema, dict):
            continue
        # ROA body 对象：展开 properties
        if p.get("in") == "body" and schema.get("type") == "object":
            for fname, fschema in schema.get("properties", {}).items():
                if isinstance(fschema, dict) and _is_required(fschema):
                    fields.append(fname)
            continue
        if _is_required(schema):
            name = p.get("name", "")
            if name:
                fields.append(name)
    return fields


def _extract_returned_fields(api: dict) -> list[str]:
    """抽取 API 的顶层返回字段名"""
    fields: list[str] = []
    seen: set[str] = set()
    for code, resp in api.get("responses", {}).items():
        schema = resp.get("schema", {})
        if not isinstance(schema, dict):
            continue
        for fname in schema.get("properties", {}).keys():
            if fname in seen or fname == "RequestId":
                continue
            seen.add(fname)
            fields.append(fname)
    return fields


def build_dependency_graph(apis_dir: Path) -> dict:
    """
    构建候选依赖图:
      producers[field] -> list of API names that return this field
      consumers[api]   -> list of required input field names
    """
    producers: dict[str, list[str]] = defaultdict(list)
    consumers: dict[str, list[str]] = {}

    for afile in sorted(apis_dir.glob("*.json")):
        try:
            api = json.loads(afile.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        api_name = api.get("api", afile.stem)

        required = _extract_required_inputs(api)
        consumers[api_name] = required

        for fname in _extract_returned_fields(api):
            producers[fname].append(api_name)

    return {"producers": dict(producers), "consumers": consumers}


# 视为"来自外部"的通用输入，不计入依赖推断
_EXTERNAL_INPUTS = {
    "RegionId", "ZoneId", "ClientToken", "PageNumber", "PageSize",
    "MaxResults", "NextToken", "Name", "ResourceGroupId",
    "OwnerId", "OwnerAccount", "ResourceOwnerAccount", "ResourceOwnerId",
    "DryRun", "AcceptLanguage",
}


def render_dependency_patterns(
    graph: dict, *, product: str, display_name: str
) -> str:
    """把候选依赖图渲染为 capability-patterns.md"""
    producers: dict[str, list[str]] = graph["producers"]
    consumers: dict[str, list[str]] = graph["consumers"]

    # 按"资源生产者"组织：哪些创建类 API 产出了哪些 ID，谁消费
    create_prefixes = ("Create", "Allocate", "Apply", "Register")

    # api_name → list of ID-like fields it produces
    produced_by_api: dict[str, list[str]] = defaultdict(list)
    for field_name, api_list in producers.items():
        if field_name.endswith("Id") or field_name.endswith("Ids"):
            for api in api_list:
                produced_by_api[api].append(field_name)

    # 只保留创建类 + 产出 ID 的
    creators = [
        (api, sorted(set(fields)))
        for api, fields in sorted(produced_by_api.items())
        if api.startswith(create_prefixes) and fields
    ]

    lines = [
        f"# {display_name} 能力依赖图（自动推断）",
        "",
        "> 本文档由 `build_skill.py` 基于 **API 返回字段 → 其他 API 输入参数** 的名称匹配",
        "> 自动生成，展示产品内各能力之间的潜在依赖关系。",
        ">",
        "> **阅读提示**：",
        "> - 这是 **候选依赖图**，需要结合产品理解判断真实依赖。",
        "> - 同名字段不一定语义相同（可能有假阳性）。",
        "> - 某些资源可能有多条获取路径（创建 / 查询已有资源皆可）。",
        '> - 人工沉淀的"典型业务场景依赖链"请追加在文末的 `## 人工沉淀场景` 区域。',
        "",
        "## 资源生产者（Resource Producers）",
        "",
        '下列"创建/分配"类能力会产出资源 ID，被其他能力作为必填输入消费。',
        "",
    ]

    if not creators:
        lines.append("> （本产品未检测到产出 ID 的创建类能力）")
        lines.append("")
    else:
        for api, fields in creators:
            # 找消费者
            consumer_set: set[str] = set()
            for f in fields:
                for consuming_api, reqs in consumers.items():
                    if consuming_api == api:
                        continue
                    if f in reqs:
                        consumer_set.add(consuming_api)

            lines.append(f"### `{api}`")
            lines.append("")
            lines.append(f"产出：{', '.join(f'`{f}`' for f in fields)}")
            lines.append("")
            if consumer_set:
                lines.append(f"被 **{len(consumer_set)}** 个能力消费：")
                for c in sorted(consumer_set)[:20]:
                    lines.append(f"- `{c}`")
                if len(consumer_set) > 20:
                    lines.append(f"- … 共 {len(consumer_set)} 个（省略 {len(consumer_set) - 20}）")
            else:
                lines.append("> 暂未发现本产品内消费者（可能被跨产品引用）")
            lines.append("")

    # 外部输入
    all_produced = set(producers.keys())
    external_usage: dict[str, int] = defaultdict(int)
    for api, reqs in consumers.items():
        for r in reqs:
            if not r:
                continue
            if r in all_produced:
                continue
            if r in _EXTERNAL_INPUTS:
                continue
            external_usage[r] += 1

    lines.append("## 外部输入（本产品内无生产者）")
    lines.append("")
    lines.append("这些必填字段在产品内找不到返回它们的能力——意味着需要从其他产品或用户直接输入：")
    lines.append("")

    if external_usage:
        for field_name, count in sorted(
            external_usage.items(), key=lambda x: (-x[1], x[0])
        )[:30]:
            lines.append(f"- `{field_name}` — 被 {count} 个能力要求")
        if len(external_usage) > 30:
            lines.append(f"- … 共 {len(external_usage)} 个外部输入字段")
    else:
        lines.append("> 未检测到外部输入。")
    lines.append("")

    # 人工沉淀占位
    lines.append("## 人工沉淀场景")
    lines.append("")
    lines.append("以下区域用于补充**典型业务场景的能力依赖链**，不会被自动生成覆盖：")
    lines.append("")
    lines.append("<!-- 以下内容由人工维护 -->")
    lines.append("")
    lines.append("- [ ] 场景 1：__________")
    lines.append("- [ ] 场景 2：__________")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SKILL.md 模板
# ---------------------------------------------------------------------------


SKILL_MD_TEMPLATE = """---
name: aliyun-{slug}-api
description: |
  阿里云 {display_name} 产品能力与机制认知 skill，面向 AI PRD 设计场景。
  当用户在做涉及阿里云 {display_name} 的产品设计、方案评估、可行性判断、能力调研时使用。
  覆盖 {display_name} 全部 {total_apis} 个 API 所表达的能力，组织为 {group_count} 个能力分区：{group_titles_inline}。
  典型触发场景：评估"这个需求能否基于阿里云 {display_name} 现有能力实现"、梳理"要做 X 功能会依赖哪些底层能力"、判断"某个产品行为的输入输出契约和约束"、调研"能力的异步性、计费维度、配额边界、废弃状态"。
  当用户提到 {keywords} 等相关场景时，应使用此 skill。
---

# 阿里云 {display_name} 能力与机制认知 skill

## 定位

本 skill **不是** API 调用手册，而是供 AI Agent 在做 **PRD 设计** 时，快速认知阿里云 {display_name} 的 **能力边界、机制约束、能力依赖** 的查询接口。

典型使用场景：
- 评估某个产品需求能否基于 {display_name} 现有能力实现
- 梳理实现某个功能会用到哪些能力、能力间的依赖顺序
- 理解某个能力的输入/输出契约（不是为了调用，而是为了理解产品模型）
- 判断能力的异步性、计费维度、配额边界、废弃状态等非功能属性

**与运行时调用的区别**：PRD 场景关心"有什么、怎么组合、约束在哪"，而非"怎么把 HTTP 请求拼对"。因此输出侧重语义理解，不做参数拼装。

## 数据结构

数据位于 `data/{product}/`，三层渐进披露：

| 层 | 文件 | 用途 |
|---|---|---|
| L0 | `index.json` | 能力分区骨架：{group_count} 个分组的 slug / 中文名 / API 数量 |
| L1 | `groups/<slug>.json` | 单个能力分区内所有 API 的签名摘要 |
| L2 | `apis/<ApiName>.json` | 单个 API 的完整契约：描述、参数、响应结构、错误码、示例 |

## 查询工具

所有查询通过 `scripts/query.py` 执行（产品无关，自动检测 `data/` 下的产品目录）。

```bash
SCRIPT="<本skill目录>/scripts/query.py"

# 产品能力分区全貌
python3 $SCRIPT capabilities

# 深入某个能力分区
python3 $SCRIPT group <slug>

# 按关键词搜索能力
python3 $SCRIPT search "<关键词>"

# 查看某个 API 所表达能力的完整契约
python3 $SCRIPT detail <ApiName>
python3 $SCRIPT detail <ApiName> --full     # 含错误码详情与示例

# 理解约束边界与演进信号
python3 $SCRIPT constraints <ApiName>       # 错误码 → 配额/状态/权限边界
python3 $SCRIPT deprecated                  # 产品中已废弃的能力

# 地域可用性
python3 $SCRIPT endpoint [region]
```

## 推荐查询路径

- **能力调研**：`capabilities` → `group <slug>` → `detail <ApiName>`
- **方案评估**：`search "<关键词>"` → `detail` 多个候选 → 查看 `references/capability-patterns.md`
- **机制理解**：`detail <ApiName> --full` → `constraints <ApiName>`

## 能力分区速查

| Slug | 能力分区 | API 数 | 核心产品能力（自动合成） |
|---|---|---:|---|
{capability_table}

## 回答 PRD 问题的规范

当 Agent 基于本 skill 回答 PRD 相关问题时：

1. **先给能力判断**：明确说"现有能力可以支持"/"部分支持，需要补 X"/"现有能力不支持"
2. **指出用到哪些能力分区**：列出相关 slug + 用途（不是 API 名列表）
3. **说明能力契约**：对关键能力说清楚输入什么、输出什么、哪些字段是约束
4. **标注机制特性**：异步/同步、幂等性、计费维度、配额限制、废弃状态
5. **给出依赖顺序**：若涉及多个能力，引用 `references/capability-patterns.md` 的依赖图

**不要** 贴大段 JSON / 把 API 参数原样输出给用户。PRD 读者关心的是产品模型，不是 HTTP 字段。

## 能力依赖模式

`references/capability-patterns.md` 自动推断了本产品内的候选依赖图：
- **资源生产者**：哪些创建类能力产出了什么 ID，被谁消费
- **外部输入**：哪些必填字段在本产品内无生产者，需跨产品或用户输入

自动推断**不能覆盖** 跨产品交互、产品设计哲学、典型业务场景依赖链——
这些需要在 `capability-patterns.md` 的 `## 人工沉淀场景` 区域追加。
"""


# ---------------------------------------------------------------------------
# 辅助：frontmatter 触发关键词 & 分组标题 inline
# ---------------------------------------------------------------------------


def _extract_keywords(display_name: str, groups: list[dict]) -> str:
    kws = [display_name]
    for g in groups[:12]:
        title = g.get("title", "").strip()
        if title and title != "其他" and title not in kws:
            kws.append(title)
    return "、".join(kws)


def _group_titles_inline(groups: list[dict], limit: int = 10) -> str:
    titles = [g.get("title", "") for g in groups if g.get("title")]
    if len(titles) > limit:
        return "、".join(titles[:limit]) + f" 等 {len(titles)} 类"
    return "、".join(titles)


def _capability_table(groups: list[dict], groups_dir: Path) -> str:
    """为每行合成"核心产品能力"列"""
    rows = []
    for g in groups:
        slug = g.get("slug", "")
        title = g.get("title", "")
        count = g.get("count", 0)

        desc = "—"
        gfile = groups_dir / f"{slug}.json"
        if gfile.exists():
            try:
                group_data = json.loads(gfile.read_text(encoding="utf-8"))
                desc = synthesize_capability_desc(group_data)
            except json.JSONDecodeError:
                pass

        # 转义 md table 分隔符
        safe_desc = desc.replace("|", "\\|")
        rows.append(f"| {slug} | {title} | {count} | {safe_desc} |")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# SKILL.md 渲染
# ---------------------------------------------------------------------------


def build_skill_md(index: dict, groups_dir: Path, category: str = "") -> str:
    product = index.get("product", "Unknown")
    groups = index.get("groups", [])
    slug = product_to_slug(product)
    display_name = extract_display_name(product, groups, category=category)
    total_apis = index.get("totalApis", sum(g.get("count", 0) for g in groups))

    return SKILL_MD_TEMPLATE.format(
        slug=slug,
        product=product,
        display_name=display_name,
        total_apis=total_apis,
        group_count=len(groups),
        group_titles_inline=_group_titles_inline(groups),
        keywords=_extract_keywords(display_name, groups),
        capability_table=_capability_table(groups, groups_dir),
    )


# ---------------------------------------------------------------------------
# 目录层级解析
# ---------------------------------------------------------------------------


def load_catalog_categories(source_dir: Path) -> dict[str, str]:
    """从 splitter 产出目录读 _catalog.json，返回 {product_dir_name: category}"""
    catalog_path = source_dir / "_catalog.json"
    if not catalog_path.exists():
        return {}
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    result: dict[str, str] = {}
    for entry in catalog.get("products", []):
        name = entry.get("product", "")
        cat = entry.get("category", "")
        if name:
            result[name] = cat
    return result


def scan_api_meta_categories(api_meta_dir: Path) -> dict[str, str]:
    """扫描 api_metadata 目录，返回 {product_stem: relative_parent_path}"""
    if not api_meta_dir.exists():
        return {}
    result: dict[str, str] = {}
    for f in api_meta_dir.rglob("*.json"):
        rel = f.relative_to(api_meta_dir)
        stem = f.stem
        parent = str(rel.parent) if rel.parent != Path(".") else ""
        result.setdefault(stem, parent)
    return result


# ---------------------------------------------------------------------------
# 单产品构建
# ---------------------------------------------------------------------------


def build_one(
    product_data_dir: Path,
    skill_dir: Path,
    query_template: Path,
    *,
    category: str = "",
    force: bool = False,
    stats: BuildStats,
) -> bool:
    index_file = product_data_dir / "index.json"
    if not index_file.exists():
        stats.warnings.append(f"跳过 {product_data_dir.name}: 缺少 index.json")
        stats.products_skipped += 1
        return False

    try:
        index = json.loads(index_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        stats.errors.append(f"{product_data_dir.name}: index.json 解析失败: {e}")
        stats.products_skipped += 1
        return False

    product = index.get("product", product_data_dir.name)

    if skill_dir.exists() and not force:
        stats.warnings.append(
            f"跳过 {product}: {skill_dir} 已存在（--force 可覆盖）"
        )
        stats.products_skipped += 1
        return False

    if skill_dir.exists() and force:
        shutil.rmtree(skill_dir)
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "scripts").mkdir()
    (skill_dir / "references").mkdir()
    (skill_dir / "data").mkdir()

    # 数据
    data_dst = skill_dir / "data" / product
    shutil.copytree(product_data_dir, data_dst)
    for _ in data_dst.rglob("*.json"):
        stats.files_written += 1

    # query.py
    if not query_template.exists():
        stats.errors.append(f"query 模板不存在: {query_template}")
        return False
    shutil.copy2(query_template, skill_dir / "scripts" / "query.py")
    stats.files_written += 1

    # SKILL.md（标准版：自动填 display_name + 分区语义列）
    groups_dir = data_dst / "groups"
    skill_md = build_skill_md(index, groups_dir, category=category)
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    stats.files_written += 1

    # capability-patterns.md（自动推断的候选依赖图）
    apis_dir = data_dst / "apis"
    graph = build_dependency_graph(apis_dir)
    display_name = extract_display_name(
        product, index.get("groups", []), category=category
    )
    patterns_md = render_dependency_patterns(
        graph, product=product, display_name=display_name
    )
    (skill_dir / "references" / "capability-patterns.md").write_text(
        patterns_md, encoding="utf-8"
    )
    stats.files_written += 1

    stats.products_built += 1
    logger.info(
        "✓ %s → %s (%d APIs, %d groups, %d 生产者字段)",
        product, skill_dir.relative_to(skill_dir.parent.parent if skill_dir.parent != skill_dir.parent.parent else skill_dir.parent),
        index.get("totalApis", 0), len(index.get("groups", [])),
        len(graph["producers"]),
    )
    return True


# ---------------------------------------------------------------------------
# 批量入口
# ---------------------------------------------------------------------------


def build_all(
    source_dir: Path,
    target_dir: Path,
    *,
    api_meta_dir: Path | None = None,
    products_filter: set[str] | None = None,
    query_template: Path = DEFAULT_QUERY_TEMPLATE,
    force: bool = False,
) -> BuildStats:
    stats = BuildStats()

    if not source_dir.is_dir():
        stats.errors.append(f"源目录不存在: {source_dir}")
        return stats

    # 分类映射：优先 catalog，回退到 api_meta 扫描，再回退到扁平
    categories = load_catalog_categories(source_dir)
    if not categories and api_meta_dir is not None:
        categories = scan_api_meta_categories(api_meta_dir)
        if categories:
            logger.info("从 %s 扫描到 %d 个产品的分类路径", api_meta_dir, len(categories))
    elif categories:
        logger.info("从 _catalog.json 读取 %d 个产品的分类路径", len(categories))
    else:
        logger.warning("未找到分类信息（无 _catalog.json 且未传 --api-meta），将扁平输出")

    product_dirs = sorted(
        d for d in source_dir.iterdir()
        if d.is_dir() and (d / "index.json").exists()
    )
    logger.info("发现 %d 个产品", len(product_dirs))

    target_dir.mkdir(parents=True, exist_ok=True)

    for pdir in product_dirs:
        if products_filter and pdir.name not in products_filter:
            continue

        category = categories.get(pdir.name, "")
        # 计算最终 skill 目录
        product_name = pdir.name  # 回退值
        try:
            idx = json.loads((pdir / "index.json").read_text(encoding="utf-8"))
            product_name = idx.get("product", pdir.name)
        except (json.JSONDecodeError, OSError):
            pass
        slug = product_to_slug(product_name)
        skill_folder = f"aliyun-{slug}-api"

        if category:
            skill_dir = target_dir / category / skill_folder
        else:
            skill_dir = target_dir / skill_folder

        build_one(
            pdir, skill_dir, query_template,
            category=category, force=force, stats=stats,
        )

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
        description="阿里云 API skill 批量生成器（标准版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 从 splitter 批量输出 + _catalog.json 生成按分类组织的 skill
  python build_skill.py output/ --target skills/

  # 若 splitter 在 single-product 模式下生成（无 _catalog.json），
  # 可用 --api-meta 指向原始元数据目录，从中扫描分类
  python build_skill.py output/ --target skills/ --api-meta api_metadata/

  # 仅构建指定产品
  python build_skill.py output/ --target skills/ --products Vpc,Ecs

  # 覆盖已存在的 skill 目录
  python build_skill.py output/ --target skills/ --force
        """,
    )
    parser.add_argument("source_dir", type=Path,
                        help="splitter 产出目录")
    parser.add_argument("--target", "-t", type=Path, required=True,
                        help="skill 输出根目录")
    parser.add_argument("--api-meta", type=Path, default=None,
                        help="原 api_metadata 目录（缺少 _catalog.json 时的回退分类来源）")
    parser.add_argument("--products", type=str, default=None,
                        help="仅构建指定产品（按 splitter 输出目录名匹配，逗号分隔）")
    parser.add_argument("--query-template", type=Path, default=DEFAULT_QUERY_TEMPLATE,
                        help="query.py 模板路径")
    parser.add_argument("--force", "-f", action="store_true",
                        help="覆盖已存在的 skill 目录")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    args = parser.parse_args()
    setup_logging(args.verbose)

    products_filter = None
    if args.products:
        products_filter = set(p.strip() for p in args.products.split(","))

    t0 = time.time()
    stats = build_all(
        args.source_dir, args.target,
        api_meta_dir=args.api_meta,
        products_filter=products_filter,
        query_template=args.query_template,
        force=args.force,
    )
    elapsed = time.time() - t0

    print("\n" + "=" * 60)
    print(f"  skill 构建完成 ({elapsed:.1f}s)")
    print("=" * 60)
    print(f"  产品构建: {stats.products_built}")
    print(f"  产品跳过: {stats.products_skipped}")
    print(f"  文件生成: {stats.files_written}")
    if stats.errors:
        print(f"\n  ⚠ 错误 ({len(stats.errors)}):")
        for e in stats.errors[:10]:
            print(f"    - {e}")
    if stats.warnings:
        print(f"\n  ⚡ 警告 ({len(stats.warnings)}):")
        for w in stats.warnings[:10]:
            print(f"    - {w}")

    sys.exit(1 if stats.errors else 0)


if __name__ == "__main__":
    main()
