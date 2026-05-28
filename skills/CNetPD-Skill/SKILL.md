---
name: CNetPD-Skill
description: |
  Cloud Networking PD Skill. 面向云网络产品设计与 PRD 推理，提供跨云厂商网络能力地图。
  当前内置 Alibaba Cloud 与 AWS 网络产品知识库；AWS 数据来自 aws/api-models-aws Smithy JSON AST。
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

不被 `npx skills add` 支持的 agent，使用 GitHub 主页安装/更新：

1. 打开 `https://github.com/benjamin1108/CNetPD-Skill-Builder`。
2. 按该 agent 的官方 skill 安装方式，把仓库中的 `skills/CNetPD-Skill/` 安装或覆盖到它的 skill 目录。
3. 如果 agent 需要直接的 skill 源目录，使用 `https://github.com/benjamin1108/CNetPD-Skill-Builder/tree/main/skills/CNetPD-Skill`。
4. 安装后运行 `python3 $SCRIPT version` 检查版本。

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
| `public-access` | 公网访问 | aliyun/Vpc、aliyun/Alb、aliyun/Nlb、aliyun/Ga、aws/ec2-networking、aws/elastic-load-balancing-v2、aws/cloudfront、aws/global-accelerator、aws/route-53 |
| `load-balancing` | 负载均衡选型 | aliyun/Slb、aliyun/Alb、aliyun/Nlb、aliyun/Gwlb、aws/elastic-load-balancing-v2、aws/elastic-load-balancing、aws/vpc-lattice |
| `cross-region` | 跨地域互联 | aliyun/Cbn、aliyun/Ga、aws/ec2-networking、aws/networkmanager、aws/global-accelerator、aws/route-53 |
| `hybrid-cloud` | 混合云接入 | aliyun/Vpc、aliyun/ExpressConnectRouter、aws/ec2-networking、aws/direct-connect、aws/networkmanager、aws/interconnect |
| `private-connect` | 私网打通 | aliyun/VpcPeer、aliyun/Cbn、aliyun/Privatelink、aws/ec2-networking、aws/vpc-lattice、aws/servicediscovery、aws/app-mesh |
| `ip-management` | IP 地址管理 | aliyun/VpcIpam、aliyun/Eipanycast、aws/ec2-networking |
| `dns-discovery` | DNS 与服务发现 | aws/route-53、aws/route53resolver、aws/route53profiles、aws/route53globalresolver、aws/servicediscovery、aws/route53-recovery-control-config、aws/route53-recovery-readiness |
| `network-security` | 网络安全 | aliyun/Vpc、aliyun/Gwlb、aws/ec2-networking、aws/network-firewall、aws/wafv2、aws/shield、aws/fms |
| `observability` | 网络诊断与可视化 | aliyun/nis、aliyun/Vpc、aws/ec2-networking、aws/networkmonitor、aws/networkflowmonitor、aws/internetmonitor |

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
| `aws/ec2-networking` | Amazon EC2 Networking / Amazon VPC | 465 | VPC、Subnet、Transit Gateway、PrivateLink、IPAM、VPN、EIP、Security Group |
| `aws/elastic-load-balancing` | Elastic Load Balancing Classic | 29 | CLB、传统负载均衡 |
| `aws/elastic-load-balancing-v2` | Elastic Load Balancing v2 | 51 | ALB、NLB、GWLB、Listener、Target Group |
| `aws/global-accelerator` | AWS Global Accelerator | 56 | 全球加速、Anycast、Endpoint Group |
| `aws/direct-connect` | AWS Direct Connect | 63 | 专线、VIF、DX Gateway、Hybrid |
| `aws/networkmanager` | AWS Network Manager / Cloud WAN | 95 | Cloud WAN、Core Network、TGW 管理 |
| `aws/vpc-lattice` | Amazon VPC Lattice | 73 | Service Network、Service-to-service、Auth Policy |
| `aws/network-firewall` | AWS Network Firewall | 79 | 网络防火墙、Firewall Policy、Rule Group |
| `aws/fms` | AWS Firewall Manager | 42 | 防火墙治理、跨账号策略 |
| `aws/wafv2` | AWS WAF v2 | 55 | Web ACL、L7 防护 |
| `aws/waf` | AWS WAF Classic | 77 | Classic WAF |
| `aws/waf-regional` | AWS WAF Regional Classic | 81 | Regional WAF Classic |
| `aws/shield` | AWS Shield | 36 | DDoS、Protection Group |
| `aws/cloudfront` | Amazon CloudFront | 167 | CDN、Edge、Distribution |
| `aws/cloudfront-keyvaluestore` | CloudFront KeyValueStore | 6 | Edge KV、CloudFront Functions |
| `aws/route-53` | Amazon Route 53 | 71 | DNS、Health Check、Traffic Policy |
| `aws/route-53-domains` | Route 53 Domains | 34 | 域名注册、DNSSEC |
| `aws/route53resolver` | Route 53 Resolver | 68 | VPC DNS、Resolver、DNS Firewall |
| `aws/route53profiles` | Route 53 Profiles | 16 | DNS Profile、跨 VPC DNS |
| `aws/route53globalresolver` | Route 53 Global Resolver | 47 | Global DNS Resolver |
| `aws/route53-recovery-cluster` | Route 53 ARC Cluster | 4 | ARC、Routing Control |
| `aws/route53-recovery-control-config` | Route 53 ARC Control Config | 25 | ARC Control Plane |
| `aws/route53-recovery-readiness` | Route 53 ARC Readiness | 32 | Readiness Check、DR |
| `aws/servicediscovery` | AWS Cloud Map | 30 | Service Discovery、Private DNS |
| `aws/app-mesh` | AWS App Mesh | 38 | Service Mesh、Traffic Routing |
| `aws/api-gateway` | Amazon API Gateway REST | 124 | REST API、VPC Link、API Edge |
| `aws/apigatewayv2` | Amazon API Gateway v2 | 103 | HTTP API、WebSocket、VPC Link |
| `aws/apigatewaymanagementapi` | API Gateway Management API | 3 | WebSocket Connection |
| `aws/internetmonitor` | Amazon CloudWatch Internet Monitor | 16 | Internet Monitor、公网可观测 |
| `aws/networkmonitor` | Amazon CloudWatch Network Monitor | 12 | Network Monitor、Hybrid Observability |
| `aws/networkflowmonitor` | Amazon CloudWatch Network Flow Monitor | 25 | Flow Monitor、Network Telemetry |
| `aws/ec2-instance-connect` | EC2 Instance Connect | 2 | Instance Connect Endpoint、Access |
| `aws/interconnect` | AWS Interconnect | 13 | Interconnect、Hybrid |

## 回答规范

1. 先定位主题和 provider，不要直接堆 API。
2. 说明产品组合和选型依据。
3. 需要证据时再查询 `product`、`group` 或 `detail`。
4. AWS 的 `ec2-networking` 是从 EC2 Smithy 模型中按网络相关 operation 单独抽取；其他 AWS 网络产品按服务模型独立进入 `provider=aws`。
5. 需要完整模型细节时读取对应产品目录下的 `source-model.json`；常规回答优先使用 L0/L1/L2 渐进查询。
6. 标注异步/同步、配额、计费、废弃状态等非功能约束。
