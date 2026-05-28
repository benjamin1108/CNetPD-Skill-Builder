# 阿里云 API 元数据 Skill 生成工具链

这个项目把阿里云 OpenAPI 元数据转换成适合 AI Agent 渐进读取的 skill 能力包。目标不是直接调用 API，而是让 Agent 在写 PRD、方案设计、能力调研时，能稳定理解已有产品能力、输入输出契约、约束边界和跨产品组合关系。

## 数据流

```text
阿里云 API Meta
  -> api_metadata/                 原始产品元数据
  -> output/                       按产品拆分后的 L0/L1/L2 结构
  -> aliyun-<product>-api/          单产品 skill
  -> skills/aliyun-network-api/     网络域跨产品 skill
```

核心脚本：

- `download_api_metas.py`：下载阿里云 API meta 到 `api_metadata/`
- `splitter.py`：把产品级单体 JSON 拆成 L0/L1/L2 渐进披露结构
- `build_skill.py`：把拆分后的产品目录打包为单产品 skill
- `build_network_skill.py`：把 13 个网络产品重封装为网络域 skill
- `aliyun-vpc-api/scripts/query.py`：单产品 skill 查询工具模板

## 渐进披露结构

`splitter.py` 会为每个产品生成：

- `index.json`：L0 产品索引，只包含能力分区骨架
- `groups/<slug>.json`：L1 分区概览，包含 API 摘要、必填参数、关键返回字段
- `apis/<ApiName>.json`：L2 API 详情，包含完整参数、响应、错误码、示例

这种结构避免 Agent 一次读取完整 API 文档，先从产品能力分区定位，再按需下钻到具体 API 契约。

## 标准命令

下载全部元数据：

```bash
python3 download_api_metas.py
```

拆分全部产品并校验：

```bash
python3 splitter.py api_metadata --output-dir output --validate
```

只拆分指定产品：

```bash
python3 splitter.py api_metadata --output-dir output --products Vpc,Slb --validate
```

构建单产品 skill：

```bash
python3 build_skill.py output --target skills --api-meta api_metadata --products Vpc --force
```

构建网络域 skill：

```bash
python3 build_network_skill.py output --target skills --force
```

## 查询示例

查看 VPC 能力分区：

```bash
python3 aliyun-vpc-api/scripts/query.py capabilities
```

查看网络域全貌：

```bash
python3 skills/aliyun-network-api/scripts/query.py domain
```

按场景查看网络产品组合：

```bash
python3 skills/aliyun-network-api/scripts/query.py topic public-access
```

## 产物边界

`.gitignore` 默认忽略：

- `api_metadata/`：官方下载源数据，体积较大
- `output/`：可由 `splitter.py` 重建
- `skills/`：可由 `build_skill.py` / `build_network_skill.py` 重建

当前仓库跟踪了 `aliyun-vpc-api/` 作为单产品 skill 样例。若需要提交更多 skill，建议先确认策略：提交精选产物，还是只提交生成器与重建说明。

## 数据安全

元数据示例中可能包含私钥、客户端密钥等敏感样例字段。`splitter.py` 和 `convert.py` 会在生成 L2/API 详情和响应示例时清洗：

- PEM 私钥块
- `PrivateKey`
- `PrivateKeyBody`
- `ClientKey`
- `CustomDomainPrivateKey`

如果后续发现新的敏感字段，应同步扩展两个脚本里的 `SENSITIVE_EXAMPLE_FIELDS`。

## 当前注意事项

- `output/_catalog.json` 与实际 `output/` 目录可能不是同一次完整生成的结果。做正式发布前应清理并重建 `output/`。
- `splitter.py` 的中文分组 slug 映射目前对 VPC 最完整，其他产品可能 fallback 为 `group-<hash>`，后续可按重点产品补充语义化映射。
- `download_api_metas.py` 还偏一次性脚本，生产化使用前建议补充 timeout、retry、下载 manifest 和版本记录。
