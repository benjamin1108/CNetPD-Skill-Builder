"""Build the distributable CNetPD-Skill."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from . import VERSION
from .constants import (
    DEFAULT_CACHE_DIR,
    GITHUB_SKILL_SOURCE_URL,
    INSTALL_COMMAND,
    LATEST_VERSION_URL,
    PRODUCT_CODES,
    PRODUCTS,
    PROJECT_DESCRIPTION,
    PROJECT_NAME,
    PROVIDER,
    PROVIDER_DISPLAY,
    SKILL_NAME,
    SOURCE_REPO,
    SOURCE_URL,
    UPDATE_COMMAND,
    UPDATE_COMMAND_GLOBAL,
    TOPICS,
)
from .manifest import write_manifest


def expand_topic_apis(topic: dict, provider_dir: Path, max_per_product: int = 8) -> dict:
    result: dict[str, list[dict]] = {}
    keywords = [keyword.lower() for keyword in topic.get("keywords", [])]
    if not keywords:
        return result
    for ref in topic.get("products", []):
        if ref.get("provider") != PROVIDER:
            continue
        product = ref["product"]
        groups_dir = provider_dir / product / "groups"
        if not groups_dir.exists():
            continue
        matches = []
        for group_file in sorted(groups_dir.glob("*.json")):
            group = json.loads(group_file.read_text(encoding="utf-8"))
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
            result[f"{PROVIDER}/{product}"] = matches
    return result


def build_cnetpd_index_from_provider(provider_dir: Path) -> dict:
    products = []
    for meta in PRODUCTS:
        index_file = provider_dir / meta["product"] / "index.json"
        api_count = 0
        group_count = 0
        if index_file.exists():
            index = json.loads(index_file.read_text(encoding="utf-8"))
            api_count = index.get("totalApis", 0)
            group_count = len(index.get("groups", []))
        products.append({
            "provider": PROVIDER,
            "product": meta["product"],
            "slug": meta["product"].lower(),
            "display": meta["display"],
            "summary": meta["summary"],
            "coverage": meta["coverage"],
            "apiCount": api_count,
            "groupCount": group_count,
        })

    topics = []
    for topic in TOPICS:
        item = {
            "slug": topic["slug"],
            "title": topic["title"],
            "description": topic["description"],
            "products": topic["products"],
            "decisions": [{"when": when, "use": use} for when, use in topic["decisions"]],
        }
        relevant = expand_topic_apis(topic, provider_dir)
        if relevant:
            item["relevantApis"] = relevant
        topics.append(item)

    return {
        "_layer": "L-1",
        "_version": VERSION,
        "skill": SKILL_NAME,
        "project": PROJECT_NAME,
        "domain": "cloud-networking",
        "description": PROJECT_DESCRIPTION,
        "providers": [{"slug": PROVIDER, "display": PROVIDER_DISPLAY, "productCount": len(products)}],
        "productCount": len(products),
        "topicCount": len(topics),
        "products": products,
        "topics": topics,
    }


def build_cnetpd_index(data_dir: Path) -> dict:
    return build_cnetpd_index_from_provider(data_dir / "providers" / PROVIDER)


def version_info() -> dict:
    return {
        "skill": SKILL_NAME,
        "version": VERSION,
        "project": PROJECT_NAME,
        "sourceRepo": SOURCE_REPO,
        "sourceUrl": SOURCE_URL,
        "githubSkillSourceUrl": GITHUB_SKILL_SOURCE_URL,
        "latestVersionUrl": LATEST_VERSION_URL,
        "installCommand": INSTALL_COMMAND,
        "updateCommand": UPDATE_COMMAND,
        "globalUpdateCommand": UPDATE_COMMAND_GLOBAL,
        "installChannels": {
            "npx": {
                "installCommand": INSTALL_COMMAND,
                "updateCommand": UPDATE_COMMAND,
                "globalUpdateCommand": UPDATE_COMMAND_GLOBAL,
            },
            "githubHomepage": {
                "homepage": SOURCE_URL,
                "skillSource": GITHUB_SKILL_SOURCE_URL,
                "instruction": "不被 npx skills add 支持的 agent：打开 GitHub 主页，按该 agent 的官方 skill 安装方式安装或覆盖 skills/CNetPD-Skill/。",
            },
        },
    }


def write_version_file(target_dir: Path) -> Path:
    path = target_dir / "version.json"
    path.write_text(json.dumps(version_info(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def render_skill_md(index: dict, *, packaged_data: bool) -> str:
    topic_row_items = []
    for topic in index["topics"]:
        topic_products = "、".join(f"{p['provider']}/{p['product']}" for p in topic["products"])
        topic_row_items.append(f"| `{topic['slug']}` | {topic['title']} | {topic_products} |")
    topic_rows = "\n".join(topic_row_items)
    product_rows = "\n".join(
        f"| `{item['provider']}/{item['slug']}` | {item['display']} | {item['apiCount']} | "
        f"{'、'.join(item['coverage'])} |"
        for item in index["products"]
    )
    data_note = (
        f"内置 `data/` 是可离线使用的快照。查询脚本优先使用 `{DEFAULT_CACHE_DIR}`；"
        "缓存缺失或超过 7 天会尝试自动同步，失败时回退内置快照。"
        if packaged_data else
        f"`npx skills add` 安装源不内置静态 data。首次查询会自动同步到 `{DEFAULT_CACHE_DIR}`；"
        "也可以先运行 `python3 $SCRIPT sync`。如果当前环境不能联网，请改用 `dist/` 下的离线包。"
    )
    return f"""---
name: {SKILL_NAME}
description: |
  Cloud Networking PD Skill. 面向云网络产品设计与 PRD 推理，提供跨云厂商网络能力地图。
  当前内置 Alibaba Cloud 网络产品知识库；结构已按 provider 分层，后续可加入 AWS 等云厂商。
  当用户询问云网络规划、VPC/负载均衡/跨地域/混合云/私网打通/IP 治理/网络诊断方案时使用本 skill。
---

# {SKILL_NAME}

## 定位

{SKILL_NAME} 是面向产品设计和方案推理的云网络知识库。回答问题时先按场景定位，再下钻到 provider/product/API 证据。

## 查询工具

```bash
SCRIPT="<本skill目录>/scripts/query.py"

python3 $SCRIPT domain
python3 $SCRIPT providers
python3 $SCRIPT topics
python3 $SCRIPT topic <slug>
python3 $SCRIPT product <product> --provider aliyun
python3 $SCRIPT group <group> --product <product> --provider aliyun
python3 $SCRIPT detail <Api> --product <product> --provider aliyun
python3 $SCRIPT search "<关键词>"
python3 $SCRIPT data-info
python3 $SCRIPT version
python3 $SCRIPT sync
```

## 安装与自更新

使用 npx 安装到 Codex 全局 skill 目录：

```bash
{INSTALL_COMMAND}
```

检查当前 skill 版本：

```bash
python3 $SCRIPT version
```

如果版本检查提示有新版本，让 agent 执行：

```bash
{UPDATE_COMMAND}
```

如果是全局安装，执行：

```bash
{UPDATE_COMMAND_GLOBAL}
```

不被 `npx skills add` 支持的 agent，使用 GitHub 主页安装/更新：

1. 打开 `{SOURCE_URL}`。
2. 按该 agent 的官方 skill 安装方式，把仓库中的 `skills/{SKILL_NAME}/` 安装或覆盖到它的 skill 目录。
3. 如果 agent 需要直接的 skill 源目录，使用 `{GITHUB_SKILL_SOURCE_URL}`。
4. 安装后运行 `python3 $SCRIPT version` 检查版本。

## 数据更新

{data_note}

环境变量：

- `CNETPD_DATA`：强制使用指定 data 目录
- `CNETPD_CACHE_DIR`：修改默认缓存 data 目录
- `CNETPD_AUTO_SYNC=0`：关闭自动同步
- `CNETPD_SYNC_TTL_DAYS=30`：修改缓存过期天数

## 主题入口

| Slug | 主题 | 涉及产品 |
|---|---|---|
{topic_rows}

## 当前产品入口

| Product | 产品 | API 数 | 覆盖能力 |
|---|---|---:|---|
{product_rows}

## 回答规范

1. 先定位主题和 provider，不要直接堆 API。
2. 说明产品组合和选型依据。
3. 需要证据时再查询 `product`、`group` 或 `detail`。
4. 标注异步/同步、配额、计费、废弃状态等非功能约束。
"""


def copy_runtime_files(target_dir: Path, package_dir: Path) -> None:
    scripts_dir = target_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir = package_dir / "runtime"
    for name in ("query.py", "sync_data.py"):
        dst = scripts_dir / name
        shutil.copy2(runtime_dir / name, dst)
        dst.chmod(0o755)
    shutil.copy2(package_dir / "constants.py", scripts_dir / "cnetpd_constants.py")
    shutil.copy2(package_dir / "aliyun_splitter.py", scripts_dir / "aliyun_splitter.py")


def package_skill_dir(target_dir: Path) -> tuple[Path, Path]:
    zip_path = target_dir.with_suffix(".zip")
    skill_path = target_dir.with_suffix(".skill")
    for artifact in (zip_path, skill_path):
        if artifact.exists():
            artifact.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(target_dir.rglob("*")):
            archive.write(path, path.relative_to(target_dir.parent))
    shutil.copy2(zip_path, skill_path)
    return zip_path, skill_path


def prepare_target(target_dir: Path, *, force: bool) -> None:
    if target_dir.exists():
        if not force:
            raise SystemExit(f"{target_dir} already exists. Use --force to overwrite.")
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True)


def validate_source(source_dir: Path) -> list[str]:
    missing = [product for product in PRODUCT_CODES if not (source_dir / product).exists()]
    if missing:
        raise RuntimeError("missing splitter output: " + ", ".join(missing))
    return PRODUCT_CODES


def build_install_source(source_dir: Path, target_dir: Path, *, force: bool, package_dir: Path) -> dict:
    prepare_target(target_dir, force=force)
    validate_source(source_dir)
    index = build_cnetpd_index_from_provider(source_dir)
    (target_dir / "SKILL.md").write_text(render_skill_md(index, packaged_data=False), encoding="utf-8")
    copy_runtime_files(target_dir, package_dir)
    write_version_file(target_dir)
    return {
        "target": str(target_dir),
        "products_available": len(PRODUCT_CODES),
        "topics_count": len(index["topics"]),
    }


def build_skill(source_dir: Path, target_dir: Path, *, force: bool, package_dir: Path) -> dict:
    prepare_target(target_dir, force=force)
    data_dir = target_dir / "data"
    provider_dir = data_dir / "providers" / PROVIDER
    provider_dir.mkdir(parents=True)

    copied = []
    missing = []
    for product in PRODUCT_CODES:
        src = source_dir / product
        if not src.exists():
            missing.append(product)
            continue
        shutil.copytree(src, provider_dir / product)
        copied.append(product)
    if missing:
        raise RuntimeError("missing splitter output: " + ", ".join(missing))

    index = build_cnetpd_index(data_dir)
    index_path = data_dir / "_cnetpd-index.json"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_path = write_manifest(data_dir, kind="snapshot")
    (target_dir / "SKILL.md").write_text(render_skill_md(index, packaged_data=True), encoding="utf-8")
    copy_runtime_files(target_dir, package_dir)
    version_path = write_version_file(target_dir)
    zip_path, skill_path = package_skill_dir(target_dir)
    return {
        "target": str(target_dir),
        "zip": str(zip_path),
        "skill": str(skill_path),
        "products_copied": len(copied),
        "index_bytes": index_path.stat().st_size,
        "manifest_bytes": manifest_path.stat().st_size,
        "version_bytes": version_path.stat().st_size,
        "topics_count": len(index["topics"]),
    }
