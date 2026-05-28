# CNetPD-Skill-Builder

Cloud Networking PD Skill builder.

本项目用于生成 `CNetPD-Skill`：一个面向云网络产品设计和 PRD 推理的 agent skill。当前数据源是 Alibaba Cloud 网络产品 API meta；目录和数据模型已经按 `provider` 分层，后续可以继续加入 AWS 等云厂商。

## 目录结构

```text
src/cnetpd_skill_builder/       构建器源码
  constants.py                  provider、产品、主题定义
  metadata.py                   Aliyun API meta 下载
  aliyun_splitter.py            Aliyun 元数据拆分
  skill.py                      CNetPD-Skill 渲染与打包
  builder.py                    构建编排
  runtime/                      写入 skill 的运行时脚本模板
tools/
  build_cnetpd_skill.py         一键生成 CNetPD-Skill
  check_code_size.py            500 行代码门禁
.output/api_metadata/           本地下载的原始元数据，忽略提交
.output/splitter/               本地 splitter 产物，忽略提交
dist/CNetPD-Skill/              最终 skill 目录，忽略提交
dist/CNetPD-Skill.zip           最终 zip 包，忽略提交
dist/CNetPD-Skill.skill         最终 .skill 包，忽略提交
```

## 构建

一键生成：

```bash
python3 tools/build_cnetpd_skill.py
```

强制刷新云厂商 API meta 后重建：

```bash
python3 tools/build_cnetpd_skill.py --refresh-meta
```

只使用已有 `.output/splitter/`：

```bash
python3 tools/build_cnetpd_skill.py --no-prepare --source-dir .output/splitter
```

默认输出：

```text
dist/CNetPD-Skill/
dist/CNetPD-Skill.zip
dist/CNetPD-Skill.skill
```

生成的 skill 内置一份可离线使用的 `data/` 快照，同时带有 `scripts/sync_data.py`。分发后查询脚本会优先读取本地缓存：

```text
~/.cache/cnetpd-skill/data
```

缓存缺失或超过 7 天时会尝试自动同步；同步失败时回退内置快照。

## 使用生成的 Skill

```bash
python3 dist/CNetPD-Skill/scripts/query.py domain
python3 dist/CNetPD-Skill/scripts/query.py topics
python3 dist/CNetPD-Skill/scripts/query.py topic public-access
python3 dist/CNetPD-Skill/scripts/query.py product Vpc --provider aliyun
python3 dist/CNetPD-Skill/scripts/query.py detail CreateVpc --product Vpc --provider aliyun
python3 dist/CNetPD-Skill/scripts/query.py data-info
python3 dist/CNetPD-Skill/scripts/query.py sync
```

环境变量：

- `CNETPD_DATA`：强制使用指定 data 目录
- `CNETPD_CACHE_DIR`：修改默认缓存 data 目录
- `CNETPD_AUTO_SYNC=0`：关闭自动同步
- `CNETPD_SYNC_TTL_DAYS=30`：修改缓存过期天数

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

仓库只提交构建器、运行时模板和说明；不提交下载数据、拆分产物或生成后的 skill。
