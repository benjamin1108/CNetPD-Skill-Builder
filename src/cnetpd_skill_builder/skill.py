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

## 定位

{SKILL_NAME} 是面向产品设计和方案推理的云网络知识库。回答问题时先按场景定位，再下钻到 provider/product/API 证据。

## 默认视角

默认采用阿里云云网络产品设计 / PRD 视角回答问题。回答目标不是做中立百科，而是帮助阿里云网络产品做能力判断、方案设计、差距分析和 PRD 推理。

除非用户明确要求纯 AWS、纯第三方或中立选型，否则按以下立场组织答案：

1. 先判断用户问题映射到阿里云哪些网络产品、API 和能力边界。
2. 先给阿里云当前可落地方案，再说明限制、缺口和风险。
3. AWS 或其他云只作为 benchmark、竞品对标或设计启发，不替代阿里云方案主线。
4. 区分事实证据、基于证据的推断、产品设计建议；不要把推断写成官方结论。
5. 不假设内部 roadmap、未公开能力或非公开限制；没有证据时明确说本地知识库未覆盖或需要外部文档补证。

复杂 PRD 方案评审、产品选型、需求分析、跨云差距判断或架构取舍时，先读取 `references/cloud-network-product-principles.md`。简单 API 查询、字段解释、命令定位、事实核验类问题无需读取。顶层设计原则只用于思考和决策，不要在回答中说“符合/违反某条原则”或逐条背诵；做出产品判断时，用自然语言说明基于客户业务创新、技术成熟度、安全高可用、长期可复用性、成本和运维复杂度等取舍。

## 查询工具

```bash
SCRIPT="<本skill目录>/scripts/query.py"

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
python3 $SCRIPT data-info
python3 $SCRIPT version
python3 $SCRIPT sync
```

## 安装与自更新

使用 npx 安装：

```bash
{INSTALL_COMMAND}
```

检查当前 skill 版本：

```bash
python3 $SCRIPT version
```

如果版本检查提示有新版本，执行：

```bash
{UPDATE_COMMAND}
```

不被 `npx skills add` 支持的环境，使用 GitHub 主页安装/更新：

1. 打开 `{SOURCE_URL}`。
2. 按对应客户端的 skill 安装方式，把仓库中的 `skills/{SKILL_NAME}/` 安装或覆盖到它的 skill 目录。
3. 如果需要直接的 skill 源目录，使用 `{GITHUB_SKILL_SOURCE_URL}`。
4. 安装后运行 `python3 $SCRIPT version` 检查版本。

## 数据更新

{data_note}

Agent 首次使用本 skill 时，必须先运行：

```bash
python3 $SCRIPT data-info
```

`data-info` 会同时检查数据缓存和 skill 本体版本。如果输出显示 skill 本体有新版本，先执行提示的 `npx skills update CNetPD-Skill` 并开启新会话重新加载 skill。如果输出显示 `有效: no`、schema 过旧、缺少目标 provider，或查询命令报 `数据目录无效`，不要直接改用 WebSearch。先执行：

```bash
python3 $SCRIPT sync
```

如果同步因为沙箱网络限制、企业代理、DNS、TLS 或 HTTP 403/407 等原因失败，向用户申请联网权限后重试。给用户的说明保持简洁，例如：

> 需要联网初始化 CNetPD-Skill 的云网络 API 数据缓存，否则本次无法使用 skill 的本地证据链。是否允许我运行 `python3 $SCRIPT sync` 更新数据？

如果用户拒绝联网或环境确实不能访问外网，再说明本次无法使用本地 skill 数据，并请用户提供可用的 `CNETPD_DATA` 目录或离线包。

环境变量：

- `CNETPD_DATA`：强制使用指定 data 目录
- `CNETPD_CACHE_DIR`：修改默认缓存 data 目录
- `CNETPD_AUTO_SYNC=0`：关闭自动同步
- `CNETPD_SYNC_TTL_DAYS=30`：修改缓存过期天数
- `CNETPD_VERSION_CHECK=0`：关闭 `data-info` 的远端 skill 版本检查

## 主题入口

| Slug | 主题 | 涉及产品 |
|---|---|---|
{topic_rows}

## 当前产品入口

| Product | 产品 | API 数 | 覆盖能力 |
|---|---|---:|---|
{product_rows}

## 回答规范

1. 默认站在阿里云云网络 PD 视角，先定位阿里云场景、产品组合和能力边界；不要用上帝视角直接做跨云百科式罗列。
2. 说明产品组合和选型依据。
3. 需要证据时再查询 `product`、`group` 或 `detail`。
4. AWS 的 `ec2-networking` 是从 EC2 Smithy 模型中按网络相关 operation 单独抽取；其他 AWS 网络产品按服务模型独立进入 `provider=aws`。
5. 需要完整模型细节时读取对应产品目录下的 `source-model.json`；常规回答优先使用 L0/L1/L2 渐进查询。
6. 标注异步/同步、配额、计费、废弃状态等非功能约束。

## 跨云对标规则

当用户问有没有同类能力、AWS 怎么做、差距在哪里时，仍按阿里云 PD 视角输出：

1. 阿里云现有能力：产品、API、地域/账号/网络范围、同步/异步边界。
2. AWS 对标能力：只列与问题直接相关的服务和 API。
3. 差距判断：能力覆盖、治理模型、自动化程度、跨账号/跨地域/路由集成。
4. 产品启发：如果要在阿里云补齐，应补在什么产品边界里，避免破坏现有网络模型。
5. 风险与证据缺口：说明哪些来自本地 API 证据，哪些需要外部文档补证。

## 检索方法

不要把用户原句当成唯一关键词。先把问题拆成场景、资源对象、动作、范围约束和云厂商，再按以下顺序扩展查询：

1. 用 `topics` / `topic <slug>` 找候选产品和能力分区。
2. 用 `product <product> --provider <provider>` 查看产品内的 group。
3. 用短词、核心名词、动词、API 片段、参数名片段分别 `search`，避免只搜完整短语。
4. 如果一个词无结果，换成同义概念、英文/中文名、连字符/空格/驼峰拆分后的词再查。
5. 命中 API 后用 `detail` 读取约束和参数；不要只凭 API 名称下结论。
6. 只有在本地数据初始化失败、目标 provider 不存在，或 skill 明确没有覆盖相关产品时，才使用 WebSearch 补证；补证时说明本地证据链缺口。
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
