---
name: CNetPD-Skill
description: |
  Cloud Networking PD Skill. 面向云网络产品设计与 PRD 推理，提供跨云厂商网络能力地图。
  当前内置 Alibaba Cloud 网络产品知识库；结构已按 provider 分层，后续可加入 AWS 等云厂商。
  当用户询问云网络规划、VPC/负载均衡/跨地域/混合云/私网打通/IP 治理/网络诊断方案时使用本 skill。
---

# CNetPD-Skill

## 定位

CNetPD-Skill 是面向产品设计和方案推理的云网络知识库。回答问题时先按场景定位，再下钻到 provider/product/API 证据。

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
npx -y skills add benjamin1108/CNetPD-Skill-Builder --skill CNetPD-Skill -a codex -g -y
```

检查当前 skill 版本：

```bash
python3 $SCRIPT version
```

如果版本检查提示有新版本，让 agent 执行：

```bash
npx -y skills update CNetPD-Skill -y
```

如果是全局安装，执行：

```bash
npx -y skills update CNetPD-Skill -g -y
```

## 数据更新

`npx skills add` 安装源不内置静态 data。首次查询会自动同步到 `~/.cache/cnetpd-skill/data`；也可以先运行 `python3 $SCRIPT sync`。如果当前环境不能联网，请改用 `dist/` 下的离线包。

环境变量：

- `CNETPD_DATA`：强制使用指定 data 目录
- `CNETPD_CACHE_DIR`：修改默认缓存 data 目录
- `CNETPD_AUTO_SYNC=0`：关闭自动同步
- `CNETPD_SYNC_TTL_DAYS=30`：修改缓存过期天数

## 主题入口

| Slug | 主题 | 涉及产品 |
|---|---|---|
| `public-access` | 公网访问 | aliyun/Vpc、aliyun/Slb、aliyun/Alb、aliyun/Nlb、aliyun/Ga、aliyun/Eipanycast |
| `load-balancing` | 负载均衡选型 | aliyun/Slb、aliyun/Alb、aliyun/Nlb、aliyun/Gwlb |
| `cross-region` | 跨地域互联 | aliyun/Cbn、aliyun/Ga、aliyun/Vpc |
| `hybrid-cloud` | 混合云接入 | aliyun/Vpc、aliyun/ExpressConnectRouter、aliyun/Cbn |
| `private-connect` | 私网打通 | aliyun/VpcPeer、aliyun/Cbn、aliyun/Privatelink |
| `ip-management` | IP 地址管理 | aliyun/VpcIpam、aliyun/Eipanycast、aliyun/Vpc |
| `observability` | 网络诊断与可视化 | aliyun/nis、aliyun/Vpc、aliyun/Cbn |

## 当前产品入口

| Product | 产品 | API 数 | 覆盖能力 |
|---|---|---:|---|
| `aliyun/vpc` | 专有网络 VPC | 405 | 隔离网络、公网访问、VPN、IPv6、子网路由 |
| `aliyun/cbn` | 云企业网 CEN | 150 | 跨地域互联、混合云路由、流量工程 |
| `aliyun/ga` | 全球加速 GA | 160 | 跨地域加速、公网接入、海外加速 |
| `aliyun/slb` | 传统型负载均衡 CLB | 93 | 负载均衡、公网接入 |
| `aliyun/alb` | 应用型负载均衡 ALB | 85 | L7 负载均衡、HTTPS 网关、流量路由 |
| `aliyun/nlb` | 网络型负载均衡 NLB | 50 | L4 负载均衡、高并发 TCP、游戏/长连接 |
| `aliyun/gwlb` | 网关型负载均衡 GWLB | 25 | 流量牵引、网络安全编排 |
| `aliyun/nis` | 网络智能服务 NIS | 26 | 网络诊断、可视化、流量分析 |
| `aliyun/privatelink` | 私网连接 PrivateLink | 39 | VPC 间私网、SaaS 私网接入、跨账号服务暴露 |
| `aliyun/expressconnectrouter` | 高速通道路由器 ECR | 38 | 混合云路由、跨账号专线 |
| `aliyun/vpcipam` | VPC IP 地址管理 IPAM | 40 | IP 规划、地址池、CIDR 治理 |
| `aliyun/eipanycast` | 任播 EIP | 15 | 任播接入、全球统一 IP |
| `aliyun/vpcpeer` | VPC 对等连接 | 11 | VPC 互联 |

## 回答规范

1. 先定位主题和 provider，不要直接堆 API。
2. 说明产品组合和选型依据。
3. 需要证据时再查询 `product`、`group` 或 `detail`。
4. 标注异步/同步、配额、计费、废弃状态等非功能约束。
