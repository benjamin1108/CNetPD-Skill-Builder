---
name: aliyun-vpc-api
description: |
  阿里云 VPC（专有网络）产品能力与机制认知 skill，面向 AI PRD 设计场景。
  当用户在做涉及阿里云网络基础设施的产品设计、方案评估、可行性判断、能力调研时使用。
  覆盖 VPC 产品全部 404 个 API 所表达的能力，组织为 37 个能力分区：VPC/VSwitch/路由表/前缀列表/网络ACL/流日志、EIP/共享带宽、NAT、VPN 网关/IPsec/SSL-VPN/用户网关、物理专线/边界路由器/BGP、IPv4 网关/IPv6 网关/IPv6 转换、路由器接口/高速通道、全球加速、高可用虚拟IP/流量镜像、网关终端节点、故障演练等。
  典型触发场景：评估"这个需求能否基于阿里云 VPC 现有能力实现"、梳理"要做 X 功能会依赖哪些底层能力"、判断"某个产品行为的输入输出契约和约束"、调研"现有能力的异步性、计费维度、配额边界、废弃状态"。
  即使用户只是笼统地问"阿里云 VPC 能做什么"、"专有网络有哪些能力"、"想了解下阿里云网络这块"，也应使用此 skill。
---

# 阿里云 VPC 能力与机制认知 skill

## 定位

本 skill **不是** API 调用手册，而是供 AI Agent 在做 **PRD 设计** 时，快速认知阿里云 VPC 产品的 **能力边界、机制约束、能力依赖** 的查询接口。

典型使用场景：
- 评估某个产品需求能否基于 VPC 现有能力实现
- 梳理实现某个功能会用到哪些能力、能力间的依赖顺序
- 理解某个能力的输入/输出契约（不是为了调用，而是为了理解产品模型）
- 判断能力的异步性、计费维度、配额边界、废弃状态等非功能属性

**与运行时调用的区别**：PRD 场景关心"有什么、怎么组合、约束在哪"，而非"怎么把 HTTP 请求拼对"。因此输出侧重语义理解，不做参数拼装。

## 数据结构

数据位于 `data/Vpc/`，三层渐进披露：

| 层 | 文件 | 大小 | 用途 |
|---|---|---|---|
| L0 | `index.json` | ~5 KB | 能力分区骨架：37 个分组的 slug / 中文名 / API 数量 |
| L1 | `groups/<slug>.json` | ~10–25 KB | 单个能力分区内所有 API 的签名摘要（名称、一句话描述、必填/可选参数、返回字段） |
| L2 | `apis/<ApiName>.json` | ~5–30 KB | 单个 API 的完整契约：描述、参数、响应结构、错误码、示例 |

## 查询工具

所有查询通过 `scripts/query.py` 执行。

```bash
SCRIPT="<本skill目录>/scripts/query.py"

# 看产品能力全貌（37 个能力分区）
python3 $SCRIPT capabilities

# 深入某个能力分区（看该分区下有哪些 API、各自的语义）
python3 $SCRIPT group nat

# 按关键词搜索能力（跨所有分区）
python3 $SCRIPT search "SNAT"

# 查看某个 API 所表达能力的完整契约
python3 $SCRIPT detail CreateSnatEntry          # 紧凑契约（描述+参数+响应）
python3 $SCRIPT detail CreateSnatEntry --full   # 加上错误码（理解约束边界）和示例

# 理解某个能力的非功能属性
python3 $SCRIPT constraints CreateSnatEntry     # 错误码 → 配额/状态/权限边界
python3 $SCRIPT deprecated                      # 产品中已废弃的能力（演进方向参考）

# endpoint（地域可用性）
python3 $SCRIPT endpoint cn-hangzhou
```

## 推荐查询路径

### 路径 A：做能力调研（不确定产品能不能做 X）

```
capabilities          # 先看 37 个能力分区，快速定位候选区
→ group <slug>        # 深入一个分区，扫描该分区能做什么
→ detail <ApiName>    # 锁定某个能力，看契约语义
```

### 路径 B：做方案评估（需求已清晰，评估实现路径）

```
search "<关键词>"     # 跨分区定位相关能力
→ detail <Api1>       # 理解每个相关能力的契约
→ detail <Api2>
→ 查看 references/capability-patterns.md     # 了解能力组合的典型依赖
```

### 路径 C：做机制理解（想搞懂某个能力的约束）

```
detail <ApiName> --full    # 看完整契约
→ constraints <ApiName>    # 专门看错误码揭示的边界
→ 阅读 description 字段关注：异步/幂等/配额/状态机
```

## 能力分区速查

下表是 37 个能力分区的一句话描述，用于快速判断用户需求属于哪个分区。

| Slug | 能力分区 | 核心产品能力 |
|---|---|---|
| vpc | 专有网络（VPC） | 私有网络隔离域，CIDR 规划、ClassicLink |
| vrouter | 路由器 | VPC 内置虚拟路由器 |
| vswitch | 交换机 | VPC 内子网划分、可用区分布 |
| route-table | 路由表 | 自定义路由、路由表关联、路由传播 |
| prefix-list | 前缀列表 | CIDR 集合抽象，路由/ACL 规则复用 |
| dhcp-option-set | DHCP 选项集 | 自定义 DNS / 域名，VPC 级 DHCP 策略 |
| flow-log | 流日志 | 流量日志采集，用于网络审计 |
| network-acl | 网络 ACL | 子网级无状态防火墙 |
| havip | 高可用虚拟 IP | HA 场景的浮动 IP |
| traffic-mirror | 流量镜像 | 流量复制到分析节点 |
| route-target-group | 路由目标组 | 多路径路由的负载均衡目标 |
| eip | 弹性公网 IP | 独立的公网 IP 资源，可绑定到 ECS/NAT/SLB/HaVip |
| shared-bandwidth | 共享带宽 | 多 EIP 共享出口带宽 |
| physical-connection | 物理专线 | 线下机房到 VPC 的专线接入（含 LOA、QoS） |
| virtual-border-router | 边界路由器（VBR） | 物理专线在云侧的终结点 |
| bgp | BGP | 专线/VPN 场景的动态路由 |
| nat | NAT 网关 | 公网出/入方向地址转换（SNAT / DNAT / FullNAT） |
| ipv4-gateway | IPv4 网关 | VPC 公网出口的显式控制 |
| vpn-gateway | VPN 网关 | IPsec / SSL-VPN 站点/客户端接入 |
| customer-gateway | 用户网关 | IPsec 对端抽象（用户侧设备） |
| vpn-attachment | 绑定 VPN 网关实例 | VPN 连接、双隧道、BGP over IPsec |
| vpn-route-entry | 绑定转发路由器实例 | VPN 路由条目 |
| ssl-client | SSL 客户端 | SSL-VPN 客户端证书管理 |
| ssl-server | SSL 服务端 | SSL-VPN 服务端配置 |
| ipsec-server | IPsec 服务端 | IPsec 客户端模式接入（移动办公） |
| ipv6-gateway | IPv6 网关 | VPC IPv6 能力开通与出口规则 |
| ipv6-translation | IPv6 转换服务 | IPv6 ↔ IPv4 双栈过渡 |
| region | 地域 | 可用地域与可用区查询 |
| tag | 标签 | 资源级标签管理 |
| router-interface | 路由器接口 | 经典对等连接（已逐步被 TR 替代） |
| express-connect | 高速上云服务 | 高速通道（专线接入的产品化入口） |
| global-acceleration | 全球加速实例 | 跨地域加速 IP |
| gateway-endpoint | 网关终端节点 | VPC 内访问阿里云服务的私网入口 |
| resource-group | 资源组 | 资源分组/权限划分 |
| fault-simulation | 故障演练 | 网络故障模拟（混沌工程） |
| qos-policy | QoS 策略 | 专线 QoS 规则 |
| misc | 其他 | 公网 IP 地址池服务开通等 |

## 回答 PRD 问题的规范

当 Agent 基于本 skill 回答 PRD 相关问题时：

1. **先给能力判断**：明确说"现有能力可以支持"/"部分支持，需要补 X"/"现有能力不支持"
2. **指出用到哪些能力分区**：列出相关 slug + 用途（不是 API 名列表）
3. **说明能力契约**：对关键能力说清楚输入什么、输出什么、哪些字段是约束
4. **标注机制特性**：异步/同步、幂等性（是否支持 ClientToken）、计费维度、配额限制、废弃状态
5. **给出依赖顺序**：若涉及多个能力，画出依赖链或引用 `references/capability-patterns.md`

**不要** 贴大段 JSON / 把 API 参数原样输出给用户。PRD 读者关心的是产品模型，不是 HTTP 字段。

## 能力依赖模式

`references/capability-patterns.md` 收录了需要多个能力组合实现的典型产品场景，含：
- 搭建完整 VPC 网络域（VPC + VSwitch + 路由）
- VPC 实例访问公网（NAT + EIP + SNAT）
- 站点到站点 VPN（VPN 网关 + 用户网关 + 连接 + 路由）
- EIP 独立分配与绑定
- 物理专线接入（物理专线 + VBR + 路由器接口）

在评估涉及多能力组合的 PRD 时，先查阅此文档理解现有实现路径。
