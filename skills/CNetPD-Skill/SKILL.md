---
name: CNetPD-Skill
description: |
  Cloud Networking PD Skill. 面向云网络产品设计与 PRD 推理，提供跨云厂商网络能力地图。
  默认采用阿里云云网络产品设计 / PRD 视角，优先服务阿里云网络产品能力判断、方案设计和差距分析。
  当前内置 Alibaba Cloud 与 AWS 网络产品知识库；AWS 数据来自 aws/api-models-aws Smithy JSON AST。
  当用户询问云网络规划、VPC/负载均衡/跨地域/混合云/私网打通/IP 治理/网络诊断方案时使用本 skill。
---

# CNetPD-Skill

## 目标

CNetPD-Skill 是云网络产品设计和 API 证据查询 skill。默认站在阿里云云网络 PD 视角，先判断阿里云能力、限制和产品边界；AWS 只作为 benchmark、差距分析或设计启发，除非用户明确要求纯 AWS 或中立选型。

复杂 PRD 评审、产品选型、跨云差距、架构取舍时读取 `references/cloud-network-product-principles.md`。简单 API 查询、字段枚举、命令定位、事实核验不读该文件。

## 启动门禁

每次会话首次使用本 skill，先运行 `data-info`；不要直接从 `topic`、`search`、`detail` 开始。

```bash
SCRIPT="<本skill目录>/scripts/query.py"
python3 $SCRIPT data-info
```

门禁规则：

1. 出现 `CNETPD_SKILL_UPDATED: <path>`：读取 `<path>`，重跑 `data-info`，再继续。
2. 版本检查或自动更新失败：停止结论，按错误申请联网/写入权限后重试。
3. 数据无效、schema 过旧、缺 provider，或报 `数据目录无效`：运行 `python3 $SCRIPT sync`。
4. 只有用户明确要求离线继续，才可设置 `CNETPD_VERSION_CHECK=0`；答案中必须说明版本未远端确认。

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

- 安装：`npx skills add benjamin1108/CNetPD-Skill-Builder --skill CNetPD-Skill`
- 更新：`npx skills update CNetPD-Skill`
- GitHub：`https://github.com/benjamin1108/CNetPD-Skill-Builder`
- 手动安装源：`https://github.com/benjamin1108/CNetPD-Skill-Builder/tree/main/skills/CNetPD-Skill`
- 数据：`npx skills add` 安装源不内置静态 data。首次查询会自动同步到 `~/.cache/cnetpd-skill/data`；也可以先运行 `python3 $SCRIPT sync`。如果当前环境不能联网，请改用 `dist/` 下的离线包。
- 环境变量：`CNETPD_DATA`、`CNETPD_CACHE_DIR`、`CNETPD_AUTO_SYNC=0`、`CNETPD_SYNC_TTL_DAYS=30`、`CNETPD_VERSION_CHECK=0`、`CNETPD_AUTO_UPDATE=0`、`CNETPD_UPDATE_TIMEOUT_SECONDS=180`、`CNETPD_SKILL_ARCHIVE_URL`

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
