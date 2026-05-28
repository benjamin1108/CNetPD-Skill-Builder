# CNetPD-Skill-Builder

Cloud Networking PD Skill builder.

本项目用于生成 `CNetPD-Skill`：一个面向云网络产品设计和 PRD 推理的 agent skill。当前数据源包括 Alibaba Cloud 网络产品 API meta 与 AWS `aws/api-models-aws` Smithy JSON AST；目录和数据模型按 `provider` 分层。

## 目录结构

```text
src/cnetpd_skill_builder/       构建器源码
  constants.py                  provider、产品、主题定义
  metadata.py                   Aliyun API meta 下载
  aliyun_splitter.py            Aliyun 元数据拆分
  aws_metadata.py               AWS Smithy 模型下载/本地克隆复用
  aws_splitter.py               AWS Smithy 模型拆分
  indexing.py                   provider-aware L-1 索引生成
  skill.py                      CNetPD-Skill 渲染与打包
  builder.py                    构建编排
  runtime/                      写入 skill 的运行时脚本模板
tools/
  build_cnetpd_skill.py         一键生成 CNetPD-Skill
  check_code_size.py            500 行代码门禁
skills/CNetPD-Skill/            提交到 GitHub 的 npx 安装源，不内置静态 data
.output/api_metadata/           本地下载的原始元数据，按 provider 缓存，忽略提交
.output/splitter/               本地 splitter 产物，按 provider 输出，忽略提交
tmp/api-models-aws/             可选的 AWS API 模型浅克隆，用于本地分析/构建加速，忽略提交
dist/CNetPD-Skill/              最终 skill 目录，忽略提交
dist/CNetPD-Skill.zip           最终 zip 包，忽略提交
dist/CNetPD-Skill.skill         最终 .skill 包，忽略提交
```

## 开发规则

所有 skill 能力必须写在 builder 源码、模板或 runtime 源码里，再由 builder 生成最终 skill。不要把 `skills/CNetPD-Skill/` 或 `dist/CNetPD-Skill/` 当作手工修改源。

详细规则见 [AGENTS.md](AGENTS.md)。

## 构建

一键生成：

```bash
python3 tools/build_cnetpd_skill.py
```

强制刷新云厂商 API meta 后重建：

```bash
python3 tools/build_cnetpd_skill.py --refresh-meta
```

如果本地已有 AWS API 模型仓库，可直接复用，避免触发在线下载：

```bash
gh repo clone aws/api-models-aws tmp/api-models-aws -- --depth=1
python3 tools/build_cnetpd_skill.py
```

也可以显式指定：

```bash
python3 tools/build_cnetpd_skill.py --aws-models-dir tmp/api-models-aws/models
```

只使用已有 `.output/splitter/`：

```bash
python3 tools/build_cnetpd_skill.py --no-prepare --source-dir .output/splitter
```

默认输出：

```text
skills/CNetPD-Skill/
dist/CNetPD-Skill/
dist/CNetPD-Skill.zip
dist/CNetPD-Skill.skill
```

`dist/` 里的 skill 内置一份可离线使用的 `data/` 快照，同时带有 `scripts/sync_data.py`。分发后查询脚本会优先读取本地缓存：

```text
~/.cache/cnetpd-skill/data
```

缓存缺失、schema 过旧或超过 30 天时会尝试自动同步；同步失败时回退内置快照。AWS 同步默认直接拉取 `raw.githubusercontent.com/aws/api-models-aws` 中固定 Smithy version 的模型文件，避免依赖 GitHub contents API rate limit。

## npx 安装

仓库提交 `skills/CNetPD-Skill/` 作为 npx 安装源，不提交静态 data。安装后首次查询会自动同步最新 API 数据到本机缓存，不需要手动下载 data。

安装到 Codex 全局 skill 目录：

```bash
npx -y skills add benjamin1108/CNetPD-Skill-Builder --skill CNetPD-Skill -a codex -g -y
```

检查 skill 版本：

```bash
python3 ~/.codex/skills/cnetpd-skill/scripts/query.py version
```

如果提示有新版本，让 agent 执行：

```bash
npx -y skills update CNetPD-Skill -g -y
```

## GitHub 主页安装

不被 `npx skills add` 支持的 agent，可以从 GitHub 主页安装：

1. 打开 <https://github.com/benjamin1108/CNetPD-Skill-Builder>。
2. 按该 agent 的官方 skill 安装方式，把 `skills/CNetPD-Skill/` 安装或覆盖到它的 skill 目录。
3. 如果 agent 需要直接的 skill 源目录，使用 <https://github.com/benjamin1108/CNetPD-Skill-Builder/tree/main/skills/CNetPD-Skill>。
4. 安装后运行该目录里的 `scripts/query.py version` 检查版本。

## 使用生成的 Skill

```bash
python3 dist/CNetPD-Skill/scripts/query.py domain
python3 dist/CNetPD-Skill/scripts/query.py topics
python3 dist/CNetPD-Skill/scripts/query.py topic public-access
python3 dist/CNetPD-Skill/scripts/query.py product Vpc --provider aliyun
python3 dist/CNetPD-Skill/scripts/query.py detail CreateVpc --product Vpc --provider aliyun
python3 dist/CNetPD-Skill/scripts/query.py product ec2-networking --provider aws
python3 dist/CNetPD-Skill/scripts/query.py detail CreateVpc --product ec2-networking --provider aws
python3 dist/CNetPD-Skill/scripts/query.py data-info
python3 dist/CNetPD-Skill/scripts/query.py version
python3 dist/CNetPD-Skill/scripts/query.py sync
```

环境变量：

- `CNETPD_DATA`：强制使用指定 data 目录
- `CNETPD_CACHE_DIR`：修改默认缓存 data 目录
- `CNETPD_AUTO_SYNC=0`：关闭自动同步
- `CNETPD_SYNC_TTL_DAYS=30`：修改缓存过期天数

AWS 的 `ec2-networking` 是从 EC2 Smithy 模型单独抽取出的网络相关虚拟产品；其他 AWS 网络相关产品按源服务模型独立进入 `provider=aws`。每个 AWS 产品目录都会保留 `source-model.json` 原始 Smithy 模型，并按 L0/L1/L2 生成渐进加载入口。

## 代码门禁

所有非生成目录下的 Python 文件不得超过 500 行：

```bash
python3 tools/check_code_size.py
```

超过 500 行说明模块职责已经过大，需要拆分后再提交。

## 产物边界

`.gitignore` 默认忽略：

- `.output/`
- `dist/`
- `tmp/`
- Python 缓存与虚拟环境

仓库只提交构建器、运行时模板和说明；不提交下载数据、拆分产物或 `dist/` 离线包。
例外：`skills/CNetPD-Skill/` 是 npx 安装源，只包含 skill 指令和运行时脚本，不包含静态 data 快照。
