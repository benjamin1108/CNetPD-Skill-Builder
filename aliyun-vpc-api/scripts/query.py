#!/usr/bin/env python3
"""
阿里云 VPC 产品能力与机制查询工具（面向 AI PRD 设计）

不同于"API 调用助手"，本工具侧重能力与机制认知：
  - 产品提供了哪些能力分区（capabilities）
  - 某个能力分区下都有什么能力（group）
  - 某个能力的契约、操作类型、计费、废弃状态（detail）
  - 某个能力的约束边界（constraints，源自错误码类别）
  - 产品中已废弃的能力（deprecated，演进信号）

用法:
  python query.py capabilities                 # 产品 37 个能力分区全貌
  python query.py group <slug>                 # 某能力分区下所有 API
  python query.py search <关键词>              # 跨分区模糊搜索能力
  python query.py detail <API名> [--full]      # 某能力的完整契约
  python query.py constraints <API名>          # 某能力的约束边界（错误码分类）
  python query.py deprecated                   # 产品中已废弃的能力
  python query.py endpoint [region]            # 地域可用性
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 数据目录定位（产品无关：自动检测 ../data/ 下唯一子目录）
# ---------------------------------------------------------------------------


def _locate_data_dir() -> Path:
    env = os.environ.get("ALIYUN_API_DATA")
    if env:
        return Path(env)

    data_root = Path(__file__).resolve().parent.parent / "data"
    if not data_root.exists():
        return data_root  # 让后续报错提示
    subdirs = [d for d in data_root.iterdir()
               if d.is_dir() and (d / "index.json").exists()]
    if len(subdirs) == 1:
        return subdirs[0]
    if len(subdirs) > 1:
        # 多产品：用环境变量选择，或按名字首字母排序取第一个（稳定）
        names = ", ".join(sorted(d.name for d in subdirs))
        print(
            f"警告: data/ 下发现多个产品（{names}），请设置 ALIYUN_API_DATA 指定",
            file=sys.stderr,
        )
        return sorted(subdirs)[0]
    return data_root  # 空目录，后续会报错


DATA_DIR = _locate_data_dir()


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _index() -> dict:
    return _load_json(DATA_DIR / "index.json")


def _iter_groups():
    """遍历所有 groups/*.json"""
    for gfile in sorted((DATA_DIR / "groups").glob("*.json")):
        yield _load_json(gfile)


def _iter_apis():
    """遍历所有 apis/*.json"""
    for afile in sorted((DATA_DIR / "apis").glob("*.json")):
        yield _load_json(afile)


# ---------------------------------------------------------------------------
# 错误码 → 约束类别（与 splitter.py 保持语义一致）
# ---------------------------------------------------------------------------

_CONSTRAINT_CATEGORIES = {
    "ResourceNotFound": "资源不存在",
    "IncorrectStatus": "资源状态不满足",
    "IncorrectBusinessStatus": "商业状态不满足",
    "ResourceAlreadyExist": "资源已存在（重复创建）",
    "QuotaExceeded": "配额超限",
    "OperationFailed": "操作失败（运行时）",
    "OperationDenied": "操作被拒绝（策略）",
    "UnsupportedRegion": "地域不支持",
    "Forbidden": "权限不足",
    "InvalidParam": "参数无效",
    "IllegalParam": "参数非法",
    "InvalidInstanceIds": "实例 ID 无效",
    "InvalidInstanceType": "实例类型无效",
    "InvalidTagKey": "标签键无效",
    "NumberExceed": "数量超限",
    "BothEmpty": "必填组合缺失",
    "MissingParameter": "缺少必填参数",
}


def _classify_error(code: str) -> str:
    prefix = code.split(".")[0] if "." in code else code
    return _CONSTRAINT_CATEGORIES.get(prefix, prefix)


# ---------------------------------------------------------------------------
# capabilities: 产品能力分区全貌
# ---------------------------------------------------------------------------


def cmd_capabilities() -> None:
    """列出产品的 37 个能力分区"""
    index = _index()
    groups = index.get("groups", [])
    product = index.get("product", "?")
    total = index.get("totalApis", "?")
    style = index.get("style", "?")
    api_version = index.get("apiVersion", "?")

    print(f"产品: {product} (OpenAPI {style} {api_version})")
    print(f"能力分区: {len(groups)} 个，覆盖 {total} 个 API\n")
    print(f"{'Slug':<24} {'能力分区':<20} {'API数':>5}")
    print("-" * 54)
    for g in groups:
        print(f"{g['slug']:<24} {g['title']:<20} {g['count']:>5}")


# ---------------------------------------------------------------------------
# group: 能力分区内详情
# ---------------------------------------------------------------------------


def cmd_group(slug: str) -> None:
    """展示某个能力分区下的所有 API 及其语义摘要"""
    gfile = DATA_DIR / "groups" / f"{slug}.json"
    if not gfile.exists():
        # 模糊匹配
        index = _index()
        candidates = [g for g in index.get("groups", [])
                      if slug.lower() in g["slug"] or slug.lower() in g["title"].lower()]
        if candidates:
            print(f"未找到 \"{slug}\"，你是否要找:")
            for c in candidates:
                print(f"  {c['slug']}  ({c['title']}, {c['count']} APIs)")
        else:
            print(f"未找到能力分区 \"{slug}\"。运行 `python query.py capabilities` 查看全部。")
        return

    group = _load_json(gfile)
    title = group.get("title", slug)
    apis = group.get("apis", [])

    print(f"【{title}】({slug}) — {len(apis)} 个能力\n")
    for api in apis:
        name = api.get("name", "")
        summary = api.get("summary", "")
        op = api.get("operationType", "")
        req = api.get("required", [])
        ret = api.get("returns", [])
        deprecated = " ⚠ 已废弃" if api.get("deprecated") else ""
        err = api.get("errorCount", 0)

        op_str = f" [{op}]" if op else ""
        print(f"  {name}{op_str}{deprecated}")
        print(f"    {summary}")
        if req:
            print(f"    必填契约: {', '.join(req)}")
        if ret:
            print(f"    返回模型: {', '.join(ret[:8])}{' …' if len(ret) > 8 else ''}")
        if err:
            print(f"    约束信号: {err} 个错误码")
        print()


# ---------------------------------------------------------------------------
# search: 跨分区搜索能力
# ---------------------------------------------------------------------------


def cmd_search(keyword: str) -> None:
    """跨所有能力分区搜索匹配的能力"""
    kw = keyword.lower()
    results = []
    for group in _iter_groups():
        slug = group.get("group", "")
        title = group.get("title", "")
        for api in group.get("apis", []):
            name = api.get("name", "")
            summary = api.get("summary", "")
            haystack = f"{name} {summary}".lower()
            if kw in haystack:
                results.append({
                    "name": name,
                    "summary": summary,
                    "group": slug,
                    "groupTitle": title,
                    "operationType": api.get("operationType", ""),
                    "required": api.get("required", []),
                    "deprecated": api.get("deprecated", False),
                })

    if not results:
        print(f"未找到匹配 \"{keyword}\" 的能力。")
        print("提示: 能力语义搜索建议用英文关键词（Vpc/Nat/Snat/Vpn/Eip/Route 等），")
        print("     或先运行 `capabilities` 浏览分区骨架再深入。")
        return

    by_group: dict[str, list] = defaultdict(list)
    for r in results:
        by_group[f"{r['groupTitle']} ({r['group']})"].append(r)

    print(f"找到 {len(results)} 个匹配 \"{keyword}\" 的能力:\n")
    for label, apis in by_group.items():
        print(f"【{label}】")
        for a in apis:
            op = f" [{a['operationType']}]" if a['operationType'] else ""
            dep = " ⚠已废弃" if a['deprecated'] else ""
            req = ", ".join(a["required"]) if a["required"] else "无必填"
            print(f"  {a['name']}{op}{dep}")
            print(f"    {a['summary']}")
            print(f"    必填: {req}")
        print()


# ---------------------------------------------------------------------------
# detail: 能力完整契约（PRD 视角）
# ---------------------------------------------------------------------------


def cmd_detail(api_name: str, full: bool = False) -> None:
    """展示某个能力的完整契约，PRD 设计视角"""
    api_file = DATA_DIR / "apis" / f"{api_name}.json"
    if not api_file.exists():
        apis_dir = DATA_DIR / "apis"
        candidates = [f.stem for f in apis_dir.glob("*.json")
                      if api_name.lower() in f.stem.lower()]
        if candidates:
            print(f"未找到 \"{api_name}\"，你是否要找:")
            for c in candidates[:10]:
                print(f"  {c}")
        else:
            print(f"未找到能力 \"{api_name}\"。")
        return

    api = _load_json(api_file)

    # --- 头部：能力标识 + 非功能属性 ---
    print(f"能力: {api.get('api', api_name)}")
    print(f"分区: {api.get('group', '')}")
    print(f"标题: {api.get('title', '')}")

    op = api.get("operationType", "")
    if op:
        print(f"操作类型: {op}")
    if api.get("deprecated"):
        print("状态: ⚠ 已废弃")

    desc = api.get("description", "")
    if desc:
        # 仅取前若干行避免噪音，但保留关键语义
        lines = [line for line in desc.split("\n") if line.strip()]
        print("\n语义说明:")
        for line in lines[:8]:
            print(f"  {line.strip()}")
        if len(lines) > 8:
            print(f"  … （省略 {len(lines) - 8} 行，--full 查看全部）")

    # --- 输入契约 ---
    params = api.get("parameters", [])
    if params:
        req_list, opt_list = _categorize_params(params)
        if req_list:
            print(f"\n输入契约（必填，{len(req_list)}）:")
            for p in req_list:
                _print_param(p)
        if opt_list:
            print(f"\n行为开关（可选，{len(opt_list)}）:")
            for p in opt_list[:15]:
                _print_param(p)
            if len(opt_list) > 15:
                print(f"  … （省略 {len(opt_list) - 15} 个，--full 查看全部）")
                # 在 full 模式下会在下面重新输出全部
        if full:
            # 全量 JSON（按需查看）
            pass

    # --- 输出模型 ---
    responses = api.get("responses", {})
    if responses:
        top_fields = _extract_top_fields(responses)
        if top_fields:
            print(f"\n返回模型（顶层字段）:")
            for name, typ in top_fields:
                print(f"  {name}: {typ}")

    # --- 约束边界 ---
    error_codes = api.get("errorCodes", {})
    if error_codes:
        constraint_map = _group_errors_by_category(error_codes)
        total = sum(len(v) for v in constraint_map.values())
        print(f"\n约束边界（{total} 个错误码，按类别）:")
        for cat, codes in sorted(constraint_map.items()):
            print(f"  {cat}: {len(codes)}")
            if full:
                for c in codes[:5]:
                    print(f"    - {c}")
                if len(codes) > 5:
                    print(f"    … （省略 {len(codes) - 5}）")
        if not full:
            print("  提示: `constraints <api>` 或 --full 查看具体错误码。")

    # --- 完整描述 & 示例（仅 --full） ---
    if full and desc:
        print("\n完整描述:")
        print(desc)

    if full and api.get("responseDemo"):
        demo = api["responseDemo"]
        if isinstance(demo, list):
            json_demos = [d for d in demo if d.get("type") == "json"]
            if json_demos:
                print("\n响应示例:")
                print(json_demos[0].get("example", "")[:2000])
        elif isinstance(demo, str):
            print("\n响应示例:")
            print(demo[:2000])


def _categorize_params(params: list[dict]) -> tuple[list[dict], list[dict]]:
    """把参数分成必填 / 可选两组。把 body 对象的 properties 也展开。"""
    req, opt = [], []

    for p in params:
        schema = p.get("schema", {})
        if not isinstance(schema, dict):
            continue
        in_loc = p.get("in", "")
        name = p.get("name", "")

        # ROA body 对象：展开顶层 properties
        if in_loc == "body" and schema.get("type") == "object":
            props = schema.get("properties", {})
            for fname, fschema in props.items():
                if not isinstance(fschema, dict):
                    continue
                entry = _param_view(fname, fschema, in_loc="body")
                if _is_required(fschema):
                    req.append(entry)
                else:
                    opt.append(entry)
            continue

        entry = _param_view(name, schema, in_loc=in_loc)
        if _is_required(schema):
            req.append(entry)
        else:
            opt.append(entry)

    return req, opt


def _is_required(schema: dict) -> bool:
    val = schema.get("required", False)
    if isinstance(val, str):
        return val.lower() == "true"
    return bool(val)


def _param_view(name: str, schema: dict, *, in_loc: str = "") -> dict:
    typ = schema.get("type", "string")
    desc = schema.get("description", "")
    # 清理 markdown 文档链接
    desc = re.sub(r"\[([^\]]*)\]\(~~\d+~~\)", r"\1", desc or "")
    desc = re.sub(r"\(~~\d+~~\)", "", desc)
    first_line = desc.split("\n")[0].strip() if desc else ""
    if len(first_line) > 80:
        first_line = first_line[:77] + "..."

    view = {"name": name, "type": typ}
    if in_loc:
        view["in"] = in_loc
    if schema.get("format"):
        view["format"] = schema["format"]
    if "enum" in schema or schema.get("enumValueTitles"):
        enum_vals = schema.get("enumValueTitles") or schema.get("enum")
        if isinstance(enum_vals, dict):
            view["enum"] = list(enum_vals.keys())
        elif isinstance(enum_vals, list) and len(enum_vals) <= 10:
            view["enum"] = enum_vals
    if "default" in schema:
        view["default"] = schema["default"]
    if first_line:
        view["desc"] = first_line
    return view


def _print_param(p: dict) -> None:
    name = p.get("name", "")
    typ = p.get("type", "")
    in_loc = p.get("in", "")
    loc = f" ({in_loc})" if in_loc and in_loc not in ("query", "") else ""
    enum = p.get("enum")
    enum_str = f" ∈ {{{', '.join(str(e) for e in enum[:5])}}}" if enum else ""
    default = p.get("default")
    default_str = f" = {default}" if default is not None else ""
    print(f"  {name}: {typ}{loc}{enum_str}{default_str}")
    if p.get("desc"):
        print(f"      {p['desc']}")


def _extract_top_fields(responses: dict) -> list[tuple[str, str]]:
    """抽取 200 响应的顶层字段 (字段名, 类型)"""
    fields = []
    seen = set()
    for code, resp in responses.items():
        schema = resp.get("schema", {})
        if isinstance(schema, dict):
            props = schema.get("properties", {})
            for name, field_schema in props.items():
                if name in seen or name == "RequestId":
                    continue
                seen.add(name)
                typ = field_schema.get("type", "object") if isinstance(field_schema, dict) else "?"
                fields.append((name, typ))
    return fields


def _group_errors_by_category(error_codes: dict) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for status, errs in error_codes.items():
        if not isinstance(errs, list):
            continue
        for e in errs:
            code = e.get("errorCode", "") if isinstance(e, dict) else str(e)
            if code:
                result[_classify_error(code)].append(code)
    return dict(result)


# ---------------------------------------------------------------------------
# constraints: 能力的约束边界
# ---------------------------------------------------------------------------


def cmd_constraints(api_name: str) -> None:
    """只展示某个能力的错误码分类，方便评估约束边界"""
    api_file = DATA_DIR / "apis" / f"{api_name}.json"
    if not api_file.exists():
        print(f"未找到能力 \"{api_name}\"。")
        return

    api = _load_json(api_file)
    error_codes = api.get("errorCodes", {})
    if not error_codes:
        print(f"{api_name} 未声明错误码（无显式约束边界）")
        return

    grouped = _group_errors_by_category(error_codes)
    total = sum(len(v) for v in grouped.values())
    print(f"【{api_name}】约束边界 — {total} 个错误码\n")
    for cat, codes in sorted(grouped.items(), key=lambda x: -len(x[1])):
        print(f"{cat} ({len(codes)}):")
        for c in codes:
            print(f"  {c}")
        print()


# ---------------------------------------------------------------------------
# deprecated: 产品中已废弃的能力
# ---------------------------------------------------------------------------


def cmd_deprecated() -> None:
    """扫描所有能力，列出废弃的——是产品演进方向的参考信号"""
    deprecated = []
    for api in _iter_apis():
        if api.get("deprecated"):
            deprecated.append({
                "name": api.get("api", ""),
                "title": api.get("title", ""),
                "group": api.get("group", ""),
            })

    if not deprecated:
        print("当前产品未标记任何废弃能力。")
        return

    by_group: dict[str, list] = defaultdict(list)
    for d in deprecated:
        by_group[d["group"]].append(d)

    print(f"共 {len(deprecated)} 个已废弃能力（演进信号参考）:\n")
    for slug, items in sorted(by_group.items()):
        print(f"【{slug}】({len(items)})")
        for d in items:
            print(f"  {d['name']} — {d['title']}")
        print()


# ---------------------------------------------------------------------------
# endpoint: 地域可用性
# ---------------------------------------------------------------------------


def cmd_endpoint(region: str | None = None) -> None:
    index = _index()
    endpoints = index.get("endpoints", {})

    if not region:
        print(f"VPC 能力在 {len(endpoints)} 个地域可用:\n")
        for rid, ep in sorted(endpoints.items()):
            print(f"  {rid:<30} {ep}")
        return

    if region in endpoints:
        print(f"{region}: {endpoints[region]}")
        return

    matches = {k: v for k, v in endpoints.items() if region.lower() in k.lower()}
    if matches:
        for rid, ep in matches.items():
            print(f"{rid}: {ep}")
    else:
        print(f"未找到 \"{region}\" 对应的 endpoint。")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="阿里云 VPC 产品能力与机制查询工具（面向 AI PRD 设计）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("capabilities", help="产品能力分区全貌")
    sub.add_parser("groups", help="capabilities 的别名")  # 向后兼容

    p_group = sub.add_parser("group", help="某能力分区内的所有能力")
    p_group.add_argument("slug")

    p_search = sub.add_parser("search", help="跨分区搜索能力")
    p_search.add_argument("keyword")

    p_detail = sub.add_parser("detail", help="某能力的完整契约")
    p_detail.add_argument("api_name")
    p_detail.add_argument("--full", action="store_true", help="展开全部描述/参数/错误码/示例")

    p_con = sub.add_parser("constraints", help="某能力的约束边界（错误码分类）")
    p_con.add_argument("api_name")

    sub.add_parser("deprecated", help="产品中已废弃的能力")

    p_ep = sub.add_parser("endpoint", help="地域可用性")
    p_ep.add_argument("region", nargs="?", default=None)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if not DATA_DIR.exists():
        print(f"错误: 数据目录不存在: {DATA_DIR}", file=sys.stderr)
        print("请先运行 splitter.py 生成数据，或设置 VPC_API_DATA。", file=sys.stderr)
        sys.exit(1)

    dispatch = {
        "capabilities": lambda: cmd_capabilities(),
        "groups": lambda: cmd_capabilities(),
        "group": lambda: cmd_group(args.slug),
        "search": lambda: cmd_search(args.keyword),
        "detail": lambda: cmd_detail(args.api_name, full=args.full),
        "constraints": lambda: cmd_constraints(args.api_name),
        "deprecated": lambda: cmd_deprecated(),
        "endpoint": lambda: cmd_endpoint(args.region),
    }
    dispatch[args.command]()


if __name__ == "__main__":
    main()
