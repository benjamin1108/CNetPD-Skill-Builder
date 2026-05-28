"""Build the distributable CNetPD-Skill."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from . import VERSION
from .constants import (
    DEFAULT_CACHE_DIR,
    DEFAULT_SYNC_TTL_DAYS,
    GITHUB_SKILL_SOURCE_URL,
    INSTALL_COMMAND,
    LATEST_VERSION_URL,
    PRODUCT_CODES_BY_PROVIDER,
    PROJECT_DESCRIPTION,
    PROJECT_NAME,
    PROVIDERS,
    SKILL_NAME,
    SOURCE_REPO,
    SOURCE_URL,
    UPDATE_COMMAND,
)
from .indexing import build_cnetpd_index
from .manifest import write_manifest


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
        "installChannels": {
            "npx": {
                "installCommand": INSTALL_COMMAND,
                "updateCommand": UPDATE_COMMAND,
            },
            "githubHomepage": {
                "homepage": SOURCE_URL,
                "skillSource": GITHUB_SKILL_SOURCE_URL,
                "instruction": "不被 npx skills add 支持的环境：打开 GitHub 主页，按对应客户端的 skill 安装方式安装或覆盖 skills/CNetPD-Skill/。",
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
        f"缓存缺失或超过 {DEFAULT_SYNC_TTL_DAYS} 天会尝试自动同步，失败时回退内置快照。"
        if packaged_data else
        f"`npx skills add` 安装源不内置静态 data。首次查询会自动同步到 `{DEFAULT_CACHE_DIR}`；"
        "也可以先运行 `python3 $SCRIPT sync`。如果当前环境不能联网，请改用 `dist/` 下的离线包。"
    )
    return f"""---
name: {SKILL_NAME}
description: |
  Cloud Networking PD Skill. 面向云网络产品设计与 PRD 推理，提供跨云厂商网络能力地图。
  默认采用阿里云云网络产品设计 / PRD 视角，优先服务阿里云网络产品能力判断、方案设计和差距分析。
  当前内置 Alibaba Cloud 与 AWS 网络产品知识库；AWS 数据来自 aws/api-models-aws Smithy JSON AST。
  当用户询问云网络规划、VPC/负载均衡/跨地域/混合云/私网打通/IP 治理/网络诊断方案时使用本 skill。
---

# {SKILL_NAME}

## 目标

{SKILL_NAME} 是云网络产品设计和 API 证据查询 skill。默认站在阿里云云网络 PD 视角，先判断阿里云能力、限制和产品边界；AWS 只作为 benchmark、差距分析或设计启发，除非用户明确要求纯 AWS 或中立选型。

复杂 PRD 评审、产品选型、跨云差距、架构取舍时读取 `references/cloud-network-product-principles.md`。简单 API 查询、字段枚举、命令定位、事实核验不读该文件。

## 启动门禁

`query.py` 每次调用都会先做远端版本检查。发现本地版本小于远端版本时，默认自动执行 `{UPDATE_COMMAND}`；更新成功后停止当前命令，并输出 `CNETPD_SKILL_UPDATED: <SKILL.md路径>`。Agent 必须重新读取该 `SKILL.md` 后，再按新版说明继续原始请求；不要在旧 skill 上下文里继续给 API 结论。

每次会话首次使用本 skill，仍需先设定脚本路径并运行 `data-info` 查看数据状态；不要直接从 `topic`、`search`、`detail` 开始。

```bash
SCRIPT="<本skill目录>/scripts/query.py"
python3 $SCRIPT data-info
```

根据 `data-info` 输出处理：

1. 若输出包含 `CNETPD_SKILL_UPDATED: <path>`，先读取 `<path>` 的新版 `SKILL.md`，再重新执行必要查询并继续回答。
2. 若版本检查或自动更新因沙箱、代理、DNS、TLS、HTTP 403/407、安装目录不可写等原因失败，不要继续做 API 结论；按环境向用户申请联网或写入权限后重试。
3. 只有用户显式要求离线继续，才可设置 `CNETPD_VERSION_CHECK=0` 跳过版本检查；这种情况下必须在答案中说明 skill 版本未完成远端确认。
4. 若 `有效: no`、schema 过旧、缺少目标 provider，或查询时报 `数据目录无效`，先运行 `python3 $SCRIPT sync`。同步仍失败时才说明无法使用本地证据链，并请用户提供 `CNETPD_DATA` 或离线包。

## 证据流程

1. 拆解问题：场景、资源对象、动作、范围约束、云厂商。
2. 先用 `topics` / `topic <slug>` 定位候选产品，再用 `product <product> --provider <provider>` 看能力分区。
3. 检索不要只搜用户原句。分别搜索核心名词、动作词、API 片段、参数名、缩写、英文/中文同义词、连字符/空格/驼峰拆分词。
4. 命中 API 后用 `detail` 查参数、约束、异步性、配额、废弃状态；如果 `detail` 未展开字段枚举或模型细节，再读取本地产品 JSON 或 `source-model.json`。
5. 只有本地数据不可用、目标 provider/product 未覆盖，或本地模型明显缺少文档约束时，才使用 WebSearch 补证；回答中标注这是外部文档补证。

## 输出协议

1. 先给结论，再给证据路径和能力边界。
2. 默认先讲阿里云可落地方案，再讲限制、缺口、风险；AWS 对标只放在相关问题里。
3. 区分本地 API 模型事实、外部文档事实、基于事实的产品推断；不要把推断写成官方结论。
4. 不假设内部 roadmap、未公开能力或非公开限制。
5. 做产品判断时自然说明基于客户价值、技术成熟度、安全高可用、长期可复用性、成本和运维复杂度，不要逐条背诵顶层原则。

## 常用命令

```bash
python3 $SCRIPT domain
python3 $SCRIPT providers
python3 $SCRIPT topics
python3 $SCRIPT topic <slug>
python3 $SCRIPT product <product> --provider aliyun
python3 $SCRIPT product ec2-networking --provider aws
python3 $SCRIPT group <group> --product <product> --provider aliyun
python3 $SCRIPT detail <Api> --product <product> --provider aliyun
python3 $SCRIPT detail CreateVpc --product ec2-networking --provider aws
python3 $SCRIPT search "<关键词>"
python3 $SCRIPT version
python3 $SCRIPT sync
```

## 安装和数据

- 安装：`{INSTALL_COMMAND}`
- 更新：`{UPDATE_COMMAND}`
- GitHub：`{SOURCE_URL}`
- 手动安装源：`{GITHUB_SKILL_SOURCE_URL}`
- 数据：{data_note}
- 环境变量：`CNETPD_DATA`、`CNETPD_CACHE_DIR`、`CNETPD_AUTO_SYNC=0`、`CNETPD_SYNC_TTL_DAYS=30`、`CNETPD_VERSION_CHECK=0`、`CNETPD_AUTO_UPDATE=0`、`CNETPD_UPDATE_TIMEOUT_SECONDS=180`

## 主题入口

| Slug | 主题 | 涉及产品 |
|---|---|---|
{topic_rows}

## 当前产品入口

| Product | 产品 | API 数 | 覆盖能力 |
|---|---|---:|---|
{product_rows}
"""


def copy_runtime_files(target_dir: Path, package_dir: Path) -> None:
    scripts_dir = target_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir = package_dir / "runtime"
    for name in ("query.py", "sync_data.py"):
        dst = scripts_dir / name
        shutil.copy2(runtime_dir / name, dst)
        dst.chmod(0o755)
    shutil.copy2(package_dir / "indexing.py", scripts_dir / "indexing.py")
    shutil.copy2(package_dir / "constants.py", scripts_dir / "cnetpd_constants.py")
    shutil.copy2(package_dir / "aliyun_splitter.py", scripts_dir / "aliyun_splitter.py")
    shutil.copy2(package_dir / "aws_splitter.py", scripts_dir / "aws_splitter.py")


def copy_reference_files(target_dir: Path, package_dir: Path) -> None:
    references_dir = package_dir / "references"
    if not references_dir.exists():
        return
    shutil.copytree(references_dir, target_dir / "references")


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
    missing = []
    for provider, products in PRODUCT_CODES_BY_PROVIDER.items():
        provider_dir = source_dir / "providers" / provider
        missing.extend(f"{provider}/{product}" for product in products if not (provider_dir / product).exists())
    if missing:
        raise RuntimeError("missing splitter output: " + ", ".join(missing))
    return missing


def build_install_source(source_dir: Path, target_dir: Path, *, force: bool, package_dir: Path) -> dict:
    prepare_target(target_dir, force=force)
    validate_source(source_dir)
    data_dir = target_dir / "_index_input"
    providers_dir = data_dir / "providers"
    providers_dir.mkdir(parents=True)
    for provider in PRODUCT_CODES_BY_PROVIDER:
        shutil.copytree(source_dir / "providers" / provider, providers_dir / provider)
    index = build_cnetpd_index(data_dir)
    shutil.rmtree(data_dir)
    (target_dir / "SKILL.md").write_text(render_skill_md(index, packaged_data=False), encoding="utf-8")
    copy_runtime_files(target_dir, package_dir)
    copy_reference_files(target_dir, package_dir)
    write_version_file(target_dir)
    return {
        "target": str(target_dir),
        "products_available": sum(len(items) for items in PRODUCT_CODES_BY_PROVIDER.values()),
        "topics_count": len(index["topics"]),
    }


def build_skill(source_dir: Path, target_dir: Path, *, force: bool, package_dir: Path) -> dict:
    prepare_target(target_dir, force=force)
    data_dir = target_dir / "data"
    copied = []
    missing = []
    for provider in PRODUCT_CODES_BY_PROVIDER:
        provider_dir = data_dir / "providers" / provider
        provider_dir.mkdir(parents=True)
        for product in PRODUCT_CODES_BY_PROVIDER[provider]:
            src = source_dir / "providers" / provider / product
            if not src.exists():
                missing.append(f"{provider}/{product}")
                continue
            shutil.copytree(src, provider_dir / product)
            copied.append(f"{provider}/{product}")
    if missing:
        raise RuntimeError("missing splitter output: " + ", ".join(missing))

    index = build_cnetpd_index(data_dir)
    index_path = data_dir / "_cnetpd-index.json"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_path = write_manifest(data_dir, kind="snapshot")
    (target_dir / "SKILL.md").write_text(render_skill_md(index, packaged_data=True), encoding="utf-8")
    copy_runtime_files(target_dir, package_dir)
    copy_reference_files(target_dir, package_dir)
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
