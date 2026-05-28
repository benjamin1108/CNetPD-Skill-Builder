# CNetPD-Skill-Builder

用于生成 `CNetPD-Skill`：一个面向云网络产品设计、PRD 推理和 API 证据查询的知识库。

当前覆盖：

- Alibaba Cloud 网络产品 API 元数据
- AWS 网络产品 API 元数据，数据来自 `aws/api-models-aws`
- 跨云厂商的主题、产品、API 分组和 API 详情查询
- 本地缓存和在线数据更新

## 目录结构

```text
CNetPD-Skill-Builder/
├── src/cnetpd_skill_builder/
│   ├── constants.py         # 云厂商、产品、主题定义
│   ├── builder.py           # 构建编排
│   ├── skill.py             # Skill 渲染与打包
│   ├── indexing.py          # 跨云厂商索引
│   ├── metadata.py          # Alibaba Cloud 元数据下载
│   ├── aliyun_splitter.py   # Alibaba Cloud 元数据拆分
│   ├── aws_metadata.py      # AWS 模型下载
│   ├── aws_splitter.py      # AWS Smithy 模型拆分
│   └── runtime/
│       ├── query.py         # Skill 内查询脚本
│       └── sync_data.py     # Skill 内数据更新脚本
├── skills/CNetPD-Skill/     # 可安装的 Skill 源目录
├── tools/
│   └── build_cnetpd_skill.py
└── README.md
```

## 安装

```bash
npx skills add benjamin1108/CNetPD-Skill-Builder --skill CNetPD-Skill
```

查询脚本默认会在每次调用时检查远端版本；发现本地版本小于远端版本时，会自动执行 `npx skills update CNetPD-Skill`。如果标准更新没有更新当前脚本目录，会直接从 GitHub 下载 `skills/CNetPD-Skill/` 覆盖当前目录。更新成功后输出 `CNETPD_SKILL_UPDATED: <SKILL.md路径>` 并停止当前命令，由 Agent 重新读取新版 `SKILL.md` 后继续。手动检查版本：

```bash
python3 <Skill目录>/scripts/query.py version
```

更新：

```bash
npx skills update CNetPD-Skill
```

## 查询

```bash
SCRIPT="<Skill目录>/scripts/query.py"

python3 $SCRIPT domain
python3 $SCRIPT providers
python3 $SCRIPT topics
python3 $SCRIPT topic public-access
python3 $SCRIPT product Vpc --provider aliyun
python3 $SCRIPT product ec2-networking --provider aws
python3 $SCRIPT detail CreateVpc --product ec2-networking --provider aws
python3 $SCRIPT search "TransitGateway"
python3 $SCRIPT data-info
python3 $SCRIPT sync
```

## 数据结构

数据按云厂商组织：

```text
providers/
├── aliyun/
│   └── <product>/
│       ├── index.json
│       ├── groups/
│       └── apis/
└── aws/
    └── <product>/
        ├── index.json
        ├── source-model.json
        ├── groups/
        └── apis/
```

AWS 的 `ec2-networking` 是从 EC2 Smithy 模型中单独抽取的网络产品。其他 AWS 网络产品按各自服务模型拆分。AWS API 详情文件保留相关 Smithy 操作、输入、输出、错误和引用结构，便于按需读取细节。

## 构建

```bash
python3 tools/build_cnetpd_skill.py
```

刷新元数据后构建：

```bash
python3 tools/build_cnetpd_skill.py --refresh-meta
```

构建后会更新：

```text
skills/CNetPD-Skill/
```

离线包会生成到 `dist/`。

## 数据缓存

查询脚本优先读取本地缓存；缓存不存在、数据版本过旧或超过 30 天时会自动更新。更新失败时，会回退到离线包内置数据。

可用环境变量：

- `CNETPD_DATA`：指定数据目录
- `CNETPD_CACHE_DIR`：修改缓存目录
- `CNETPD_AUTO_SYNC=0`：关闭数据缓存自动同步
- `CNETPD_SYNC_TTL_DAYS=30`：修改缓存过期天数
- `CNETPD_VERSION_CHECK=0`：跳过 skill 版本检查
- `CNETPD_AUTO_UPDATE=0`：检查到新版本时停止查询但不自动更新
- `CNETPD_UPDATE_TIMEOUT_SECONDS=180`：修改自动更新命令超时时间
- `CNETPD_SKILL_ARCHIVE_URL`：覆盖直接更新当前目录时使用的 GitHub tarball URL

## 开发

修改 Skill 能力时，改 `src/cnetpd_skill_builder/` 下的源码，然后重新生成：

```bash
python3 tools/build_cnetpd_skill.py
```

不要把生成后的 Skill 目录当成源头手工维护。
