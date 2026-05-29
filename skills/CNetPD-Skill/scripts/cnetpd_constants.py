"""Shared provider, product, and topic definitions for CNetPD-Skill."""

from __future__ import annotations

SKILL_NAME = "CNetPD-Skill"
SKILL_VERSION = "1.4.3"
PROJECT_NAME = "CNetPD-Skill-Builder"
PROJECT_DESCRIPTION = "Cloud Networking PD Skill"
SOURCE_REPO = "benjamin1108/CNetPD-Skill-Builder"
SOURCE_URL = f"https://github.com/{SOURCE_REPO}"
GITHUB_SKILL_SOURCE_URL = f"{SOURCE_URL}/tree/main/skills/{SKILL_NAME}"
LATEST_VERSION_URL = f"https://raw.githubusercontent.com/{SOURCE_REPO}/main/version.json"
INSTALL_COMMAND = f"npx skills add {SOURCE_REPO} --skill {SKILL_NAME}"
UPDATE_COMMAND = f"npx skills update {SKILL_NAME}"
UPDATE_COMMAND_GLOBAL = UPDATE_COMMAND
SOURCE_ARCHIVE_URL = f"https://github.com/{SOURCE_REPO}/archive/refs/heads/main.tar.gz"

DATA_SCHEMA_VERSION = 2
DEFAULT_CACHE_DIR = "~/.cache/cnetpd-skill/data"
DEFAULT_SYNC_TTL_DAYS = 30

ALIYUN_PROVIDER = "aliyun"
ALIYUN_PROVIDER_DISPLAY = "Alibaba Cloud"
BASE_URL = "https://api.aliyun.com/meta/v1/"
PRODUCTS_URL = BASE_URL + "products.json"

AWS_PROVIDER = "aws"
AWS_PROVIDER_DISPLAY = "Amazon Web Services"
AWS_API_MODELS_REPO = "aws/api-models-aws"
AWS_API_MODELS_BRANCH = "main"
AWS_API_MODELS_CONTENTS_URL = f"https://api.github.com/repos/{AWS_API_MODELS_REPO}/contents/models"
AWS_API_MODELS_RAW_URL = f"https://raw.githubusercontent.com/{AWS_API_MODELS_REPO}/{AWS_API_MODELS_BRANCH}/models"

ALIYUN_PRODUCTS: list[dict] = [
    {"product": "Vpc", "display": "专有网络 VPC", "summary": "VPC/子网/路由/EIP/NAT/VPN/IPv6 等核心网络基础设施", "coverage": ["隔离网络", "公网访问", "VPN", "IPv6", "子网路由"]},
    {"product": "Cbn", "display": "云企业网 CEN", "summary": "多地域 VPC/VBR 内网互联枢纽，支持转发路由器精细路由", "coverage": ["跨地域互联", "混合云路由", "流量工程"]},
    {"product": "Ga", "display": "全球加速 GA", "summary": "跨地域用户就近接入 + 骨干网加速，公网面的加速产品", "coverage": ["跨地域加速", "公网接入", "海外加速"]},
    {"product": "Slb", "display": "传统型负载均衡 CLB", "summary": "L4/L7 综合型负载均衡，成熟稳定", "coverage": ["负载均衡", "公网接入"]},
    {"product": "Alb", "display": "应用型负载均衡 ALB", "summary": "L7 专精：HTTP/HTTPS/HTTP-2/WebSocket/gRPC/QUIC、丰富路由规则", "coverage": ["L7 负载均衡", "HTTPS 网关", "流量路由"]},
    {"product": "Nlb", "display": "网络型负载均衡 NLB", "summary": "L4 专精：千万并发、低延迟、保留源 IP", "coverage": ["L4 负载均衡", "高并发 TCP", "游戏/长连接"]},
    {"product": "Gwlb", "display": "网关型负载均衡 GWLB", "summary": "透明流量牵引到第三方/自建安全网关", "coverage": ["流量牵引", "网络安全编排"]},
    {"product": "nis", "display": "网络智能服务 NIS", "summary": "路径分析、抓包、可达性诊断、拓扑可视化", "coverage": ["网络诊断", "可视化", "流量分析"]},
    {"product": "Privatelink", "display": "私网连接 PrivateLink", "summary": "服务提供方暴露终端节点，消费方单向私网访问", "coverage": ["VPC 间私网", "SaaS 私网接入", "跨账号服务暴露"]},
    {"product": "ExpressConnectRouter", "display": "高速通道路由器 ECR", "summary": "多 VBR / 多账号 / 多地域专线路由编排", "coverage": ["混合云路由", "跨账号专线"]},
    {"product": "VpcIpam", "display": "VPC IP 地址管理 IPAM", "summary": "多 VPC/多账号 CIDR 统一规划、地址池、冲突检测", "coverage": ["IP 规划", "地址池", "CIDR 治理"]},
    {"product": "Eipanycast", "display": "任播 EIP", "summary": "同一公网 IP 在多地域发布，用户就近接入", "coverage": ["任播接入", "全球统一 IP"]},
    {"product": "VpcPeer", "display": "VPC 对等连接", "summary": "两两 VPC 直连，小规模互联", "coverage": ["VPC 互联"]},
]

AWS_PRODUCTS: list[dict] = [
    {"product": "ec2-networking", "sourceService": "ec2", "operationFilter": "ec2-networking", "display": "Amazon EC2 Networking / Amazon VPC", "summary": "从 EC2 Smithy 模型中单独抽取 VPC、Subnet、路由、网关、EIP、ENI、安全组、NACL、TGW、VPN、IPAM、PrivateLink、流量镜像和网络洞察 API", "coverage": ["VPC", "Subnet", "Transit Gateway", "PrivateLink", "IPAM", "VPN", "EIP", "Security Group"]},
    {"product": "elastic-load-balancing", "display": "Elastic Load Balancing Classic", "summary": "Classic Load Balancer API", "coverage": ["CLB", "传统负载均衡"]},
    {"product": "elastic-load-balancing-v2", "display": "Elastic Load Balancing v2", "summary": "ALB/NLB/GWLB 负载均衡、监听、规则、目标组、Trust Store", "coverage": ["ALB", "NLB", "GWLB", "Listener", "Target Group"]},
    {"product": "global-accelerator", "display": "AWS Global Accelerator", "summary": "Anycast 静态入口、跨地域流量加速和端点组", "coverage": ["全球加速", "Anycast", "Endpoint Group"]},
    {"product": "direct-connect", "display": "AWS Direct Connect", "summary": "专线连接、虚拟接口、LAG、Direct Connect Gateway", "coverage": ["专线", "VIF", "DX Gateway", "Hybrid"]},
    {"product": "networkmanager", "display": "AWS Network Manager / Cloud WAN", "summary": "Cloud WAN、核心网络、Transit Gateway 网络集中管理", "coverage": ["Cloud WAN", "Core Network", "TGW 管理"]},
    {"product": "vpc-lattice", "display": "Amazon VPC Lattice", "summary": "服务网络、服务间连接、安全策略和监听规则", "coverage": ["Service Network", "Service-to-service", "Auth Policy"]},
    {"product": "network-firewall", "display": "AWS Network Firewall", "summary": "托管网络防火墙、规则组、防火墙策略和 TLS 检查", "coverage": ["网络防火墙", "Firewall Policy", "Rule Group"]},
    {"product": "fms", "display": "AWS Firewall Manager", "summary": "跨账号集中管理 WAF、Shield、Network Firewall 等策略", "coverage": ["防火墙治理", "跨账号策略"]},
    {"product": "wafv2", "display": "AWS WAF v2", "summary": "保护 CloudFront、ALB、API Gateway、Verified Access 等资源的 Web ACL", "coverage": ["Web ACL", "L7 防护"]},
    {"product": "waf", "display": "AWS WAF Classic", "summary": "旧版 WAF 全局 API，保留用于历史资源识别", "coverage": ["Classic WAF"]},
    {"product": "waf-regional", "display": "AWS WAF Regional Classic", "summary": "旧版区域 WAF API，保留用于历史资源识别", "coverage": ["Regional WAF Classic"]},
    {"product": "shield", "display": "AWS Shield", "summary": "DDoS 防护、保护组、攻击可见性和订阅管理", "coverage": ["DDoS", "Protection Group"]},
    {"product": "cloudfront", "display": "Amazon CloudFront", "summary": "CDN 分发、缓存行为、源、函数、Key Group、实时日志", "coverage": ["CDN", "Edge", "Distribution"]},
    {"product": "cloudfront-keyvaluestore", "display": "CloudFront KeyValueStore", "summary": "CloudFront Functions 使用的边缘 Key-Value Store", "coverage": ["Edge KV", "CloudFront Functions"]},
    {"product": "route-53", "display": "Amazon Route 53", "summary": "托管区、DNS 记录、健康检查、流量策略", "coverage": ["DNS", "Health Check", "Traffic Policy"]},
    {"product": "route-53-domains", "display": "Route 53 Domains", "summary": "域名注册、联系人、转移和 DNSSEC 域名侧操作", "coverage": ["域名注册", "DNSSEC"]},
    {"product": "route53resolver", "display": "Route 53 Resolver", "summary": "VPC DNS 解析器、入站/出站端点、Resolver 规则和 DNS Firewall", "coverage": ["VPC DNS", "Resolver", "DNS Firewall"]},
    {"product": "route53profiles", "display": "Route 53 Profiles", "summary": "跨 VPC 管理 Route 53 Resolver 配置档", "coverage": ["DNS Profile", "跨 VPC DNS"]},
    {"product": "route53globalresolver", "display": "Route 53 Global Resolver", "summary": "Route 53 全局解析器相关 API", "coverage": ["Global DNS Resolver"]},
    {"product": "route53-recovery-cluster", "display": "Route 53 ARC Cluster", "summary": "Application Recovery Controller 数据面路由控制", "coverage": ["ARC", "Routing Control"]},
    {"product": "route53-recovery-control-config", "display": "Route 53 ARC Control Config", "summary": "ARC 控制面、集群、控制面板、安全规则", "coverage": ["ARC Control Plane"]},
    {"product": "route53-recovery-readiness", "display": "Route 53 ARC Readiness", "summary": "恢复就绪检查、资源集和恢复组", "coverage": ["Readiness Check", "DR"]},
    {"product": "servicediscovery", "display": "AWS Cloud Map", "summary": "服务发现命名空间、服务实例和私有 DNS 服务发现", "coverage": ["Service Discovery", "Private DNS"]},
    {"product": "app-mesh", "display": "AWS App Mesh", "summary": "服务网格、虚拟节点、虚拟路由、Gateway Route", "coverage": ["Service Mesh", "Traffic Routing"]},
    {"product": "api-gateway", "display": "Amazon API Gateway REST", "summary": "REST API 前门、资源、方法、部署、VPC Link", "coverage": ["REST API", "VPC Link", "API Edge"]},
    {"product": "apigatewayv2", "display": "Amazon API Gateway v2", "summary": "HTTP/WebSocket API、集成、路由、VPC Link", "coverage": ["HTTP API", "WebSocket", "VPC Link"]},
    {"product": "apigatewaymanagementapi", "display": "API Gateway Management API", "summary": "WebSocket 连接管理数据面 API", "coverage": ["WebSocket Connection"]},
    {"product": "internetmonitor", "display": "Amazon CloudWatch Internet Monitor", "summary": "公网路径性能与可用性监控", "coverage": ["Internet Monitor", "公网可观测"]},
    {"product": "networkmonitor", "display": "Amazon CloudWatch Network Monitor", "summary": "混合网络探针和网络路径监控", "coverage": ["Network Monitor", "Hybrid Observability"]},
    {"product": "networkflowmonitor", "display": "Amazon CloudWatch Network Flow Monitor", "summary": "工作负载网络流可见性与性能指标", "coverage": ["Flow Monitor", "Network Telemetry"]},
    {"product": "ec2-instance-connect", "display": "EC2 Instance Connect", "summary": "EC2 Instance Connect Endpoint 和 SSH 连接入口相关 API", "coverage": ["Instance Connect Endpoint", "Access"]},
    {"product": "interconnect", "display": "AWS Interconnect", "summary": "AWS Interconnect API model 中的连接和站点能力", "coverage": ["Interconnect", "Hybrid"]},
]

AWS_MODEL_VERSIONS: dict[str, str] = {
    "api-gateway": "2015-07-09",
    "apigatewaymanagementapi": "2018-11-29",
    "apigatewayv2": "2018-11-29",
    "app-mesh": "2019-01-25",
    "cloudfront": "2020-05-31",
    "cloudfront-keyvaluestore": "2022-07-26",
    "direct-connect": "2012-10-25",
    "ec2": "2016-11-15",
    "ec2-instance-connect": "2018-04-02",
    "elastic-load-balancing": "2012-06-01",
    "elastic-load-balancing-v2": "2015-12-01",
    "fms": "2018-01-01",
    "global-accelerator": "2018-08-08",
    "interconnect": "2022-07-26",
    "internetmonitor": "2021-06-03",
    "network-firewall": "2020-11-12",
    "networkflowmonitor": "2023-04-19",
    "networkmanager": "2019-07-05",
    "networkmonitor": "2023-08-01",
    "route-53": "2013-04-01",
    "route-53-domains": "2014-05-15",
    "route53-recovery-cluster": "2019-12-02",
    "route53-recovery-control-config": "2020-11-02",
    "route53-recovery-readiness": "2019-12-02",
    "route53globalresolver": "2022-09-27",
    "route53profiles": "2018-05-10",
    "route53resolver": "2018-04-01",
    "servicediscovery": "2017-03-14",
    "shield": "2016-06-02",
    "vpc-lattice": "2022-11-30",
    "waf": "2015-08-24",
    "waf-regional": "2016-11-28",
    "wafv2": "2019-07-29",
}

PROVIDERS = [
    {"slug": ALIYUN_PROVIDER, "display": ALIYUN_PROVIDER_DISPLAY, "products": ALIYUN_PRODUCTS},
    {"slug": AWS_PROVIDER, "display": AWS_PROVIDER_DISPLAY, "products": AWS_PRODUCTS},
]
PRODUCTS_BY_PROVIDER = {item["slug"]: item["products"] for item in PROVIDERS}
PRODUCT_CODES_BY_PROVIDER = {
    provider: [item["product"] for item in products]
    for provider, products in PRODUCTS_BY_PROVIDER.items()
}
ALL_PRODUCTS = [
    {"provider": provider, **product}
    for provider, products in PRODUCTS_BY_PROVIDER.items()
    for product in products
]

# Backward-compatible aliases used by the Aliyun splitter/downloader.
PROVIDER = ALIYUN_PROVIDER
PROVIDER_DISPLAY = ALIYUN_PROVIDER_DISPLAY
PRODUCTS = ALIYUN_PRODUCTS
PRODUCT_CODES = PRODUCT_CODES_BY_PROVIDER[ALIYUN_PROVIDER]
AWS_PRODUCT_CODES = PRODUCT_CODES_BY_PROVIDER[AWS_PROVIDER]

TOPICS: list[dict] = [
    {
        "slug": "public-access",
        "title": "公网访问",
        "description": "云内资源访问公网；公网用户访问云内服务。",
        "products": [
            {"provider": ALIYUN_PROVIDER, "product": "Vpc", "role": "EIP / NAT / IPv6 / 共享带宽"},
            {"provider": ALIYUN_PROVIDER, "product": "Alb", "role": "公网 L7 入口"},
            {"provider": ALIYUN_PROVIDER, "product": "Nlb", "role": "公网 L4 入口"},
            {"provider": ALIYUN_PROVIDER, "product": "Ga", "role": "跨地域公网加速"},
            {"provider": AWS_PROVIDER, "product": "ec2-networking", "role": "EIP / NAT Gateway / IGW / IPv6"},
            {"provider": AWS_PROVIDER, "product": "elastic-load-balancing-v2", "role": "ALB/NLB/GWLB 公网入口"},
            {"provider": AWS_PROVIDER, "product": "cloudfront", "role": "CDN 和边缘入口"},
            {"provider": AWS_PROVIDER, "product": "global-accelerator", "role": "Anycast 加速入口"},
            {"provider": AWS_PROVIDER, "product": "route-53", "role": "公网 DNS 和健康检查"},
        ],
        "keywords": ["EIP", "NAT", "Internet", "PublicIp", "公网", "Anycast", "Distribution", "Accelerator"],
        "decisions": [("单实例出公网", "EIP"), ("多实例共享出公网", "NAT Gateway + SNAT"), ("Web/API 公网入口", "ALB/API Gateway/CloudFront"), ("跨地域低延迟入口", "Global Accelerator 或 GA")],
    },
    {
        "slug": "load-balancing",
        "title": "负载均衡选型",
        "description": "在多后端实例之间分发流量；从 L7/L4/网关型入口判断。",
        "products": [
            {"provider": ALIYUN_PROVIDER, "product": "Slb", "role": "传统 L4/L7 兼容"},
            {"provider": ALIYUN_PROVIDER, "product": "Alb", "role": "L7、HTTPS、gRPC、内容路由"},
            {"provider": ALIYUN_PROVIDER, "product": "Nlb", "role": "L4、高并发、长连接"},
            {"provider": ALIYUN_PROVIDER, "product": "Gwlb", "role": "透明流量牵引"},
            {"provider": AWS_PROVIDER, "product": "elastic-load-balancing-v2", "role": "ALB/NLB/GWLB"},
            {"provider": AWS_PROVIDER, "product": "elastic-load-balancing", "role": "Classic Load Balancer"},
            {"provider": AWS_PROVIDER, "product": "vpc-lattice", "role": "服务到服务入口和策略"},
        ],
        "keywords": ["LoadBalancer", "Listener", "TargetGroup", "BackendServer", "HealthCheck", "Rule"],
        "decisions": [("HTTP/HTTPS/gRPC/内容路由", "ALB"), ("TCP/UDP/高并发/长连接", "NLB"), ("兼容传统架构", "CLB"), ("安全网关透明串联", "GWLB")],
    },
    {
        "slug": "cross-region",
        "title": "跨地域互联",
        "description": "多地域私网互通，或公网用户跨地域加速接入。",
        "products": [
            {"provider": ALIYUN_PROVIDER, "product": "Cbn", "role": "多地域内网互通枢纽"},
            {"provider": ALIYUN_PROVIDER, "product": "Ga", "role": "公网面跨地域加速"},
            {"provider": AWS_PROVIDER, "product": "ec2-networking", "role": "Transit Gateway / VPC Peering"},
            {"provider": AWS_PROVIDER, "product": "networkmanager", "role": "Cloud WAN / TGW 网络集中管理"},
            {"provider": AWS_PROVIDER, "product": "global-accelerator", "role": "公网 Anycast 加速"},
            {"provider": AWS_PROVIDER, "product": "route-53", "role": "DNS 流量策略与健康检查"},
        ],
        "keywords": ["TransitGateway", "CenInstance", "Bandwidth", "Accelerator", "CrossBorder", "Region", "CoreNetwork"],
        "decisions": [("私网跨地域互通", "Transit Gateway / Cloud WAN / CEN"), ("公网用户跨地域加速", "Global Accelerator / GA"), ("DNS 灾备调度", "Route 53 / ARC")],
    },
    {
        "slug": "hybrid-cloud",
        "title": "混合云接入",
        "description": "本地 IDC、办公网或其他云接入云上 VPC。",
        "products": [
            {"provider": ALIYUN_PROVIDER, "product": "Vpc", "role": "VPN Gateway / VBR"},
            {"provider": ALIYUN_PROVIDER, "product": "ExpressConnectRouter", "role": "专线路由编排"},
            {"provider": AWS_PROVIDER, "product": "ec2-networking", "role": "Site-to-Site VPN / Customer Gateway / TGW"},
            {"provider": AWS_PROVIDER, "product": "direct-connect", "role": "专线接入和 DX Gateway"},
            {"provider": AWS_PROVIDER, "product": "networkmanager", "role": "Cloud WAN 混合网络治理"},
            {"provider": AWS_PROVIDER, "product": "interconnect", "role": "Interconnect 模型能力"},
        ],
        "keywords": ["VpnGateway", "VpnConnection", "CustomerGateway", "DirectConnect", "VirtualInterface", "Bgp"],
        "decisions": [("轻量或临时连接", "VPN Gateway / Site-to-Site VPN"), ("生产级低延迟大带宽", "物理专线 / Direct Connect"), ("多账号多地域专线编排", "Cloud WAN / TGW / ECR")],
    },
    {
        "slug": "private-connect",
        "title": "私网打通",
        "description": "VPC 之间或跨账号服务之间的内网连通。",
        "products": [
            {"provider": ALIYUN_PROVIDER, "product": "VpcPeer", "role": "少量 VPC 点对点互联"},
            {"provider": ALIYUN_PROVIDER, "product": "Cbn", "role": "多 VPC 集线器互联"},
            {"provider": ALIYUN_PROVIDER, "product": "Privatelink", "role": "服务级单向私网访问"},
            {"provider": AWS_PROVIDER, "product": "ec2-networking", "role": "PrivateLink / VPC Endpoint / Peering / TGW"},
            {"provider": AWS_PROVIDER, "product": "vpc-lattice", "role": "应用服务网络"},
            {"provider": AWS_PROVIDER, "product": "servicediscovery", "role": "Cloud Map 服务发现"},
            {"provider": AWS_PROVIDER, "product": "app-mesh", "role": "服务网格流量治理"},
        ],
        "keywords": ["PeerConnection", "VpcEndpoint", "PrivateLink", "TransitGateway", "ServiceNetwork", "CloudMap", "Mesh"],
        "decisions": [("2-3 个 VPC 双向互通", "VPC Peering / VPC Peer"), ("多 VPC 或跨地域互通", "Transit Gateway / CEN"), ("只暴露服务不暴露整张网", "PrivateLink / VPC Lattice")],
    },
    {
        "slug": "ip-management",
        "title": "IP 地址管理",
        "description": "IP 资源规划、CIDR 冲突治理、公网 IP 策略。",
        "products": [
            {"provider": ALIYUN_PROVIDER, "product": "VpcIpam", "role": "CIDR 统一规划与冲突检测"},
            {"provider": ALIYUN_PROVIDER, "product": "Eipanycast", "role": "多地域同一公网 IP"},
            {"provider": AWS_PROVIDER, "product": "ec2-networking", "role": "Amazon VPC IPAM / EIP / BYOIP / Public IPv4 Pool"},
        ],
        "keywords": ["Ipam", "IpamPool", "Cidr", "Anycast", "EipAddress", "PublicIpv4Pool", "Byoip"],
        "decisions": [("普通公网 IP", "EIP"), ("企业级 CIDR 规划", "VPC IPAM"), ("自带公网地址", "BYOIP / Public IPv4 Pool"), ("多地域统一入口 IP", "Anycast EIP / Global Accelerator")],
    },
    {
        "slug": "dns-discovery",
        "title": "DNS 与服务发现",
        "description": "公网/私网 DNS、跨 VPC 解析、服务发现和恢复控制。",
        "products": [
            {"provider": AWS_PROVIDER, "product": "route-53", "role": "Hosted Zone / Record / Health Check"},
            {"provider": AWS_PROVIDER, "product": "route53resolver", "role": "VPC Resolver / DNS Firewall / Resolver Endpoint"},
            {"provider": AWS_PROVIDER, "product": "route53profiles", "role": "跨 VPC Resolver 配置"},
            {"provider": AWS_PROVIDER, "product": "route53globalresolver", "role": "全局解析器"},
            {"provider": AWS_PROVIDER, "product": "servicediscovery", "role": "Cloud Map"},
            {"provider": AWS_PROVIDER, "product": "route53-recovery-control-config", "role": "ARC 控制面"},
            {"provider": AWS_PROVIDER, "product": "route53-recovery-readiness", "role": "ARC 就绪检查"},
        ],
        "keywords": ["HostedZone", "Resolver", "DNS", "Namespace", "ServiceDiscovery", "Recovery", "RoutingControl"],
        "decisions": [("公网权威 DNS", "Route 53 Hosted Zone"), ("VPC 与本地 DNS 互通", "Route 53 Resolver"), ("服务发现", "Cloud Map"), ("灾备切流", "Route 53 ARC")],
    },
    {
        "slug": "network-security",
        "title": "网络安全",
        "description": "L3/L4/L7 网络访问控制、边缘防护、DDoS 和跨账号策略治理。",
        "products": [
            {"provider": ALIYUN_PROVIDER, "product": "Vpc", "role": "安全组 / 网络 ACL"},
            {"provider": ALIYUN_PROVIDER, "product": "Gwlb", "role": "安全网关透明串联"},
            {"provider": AWS_PROVIDER, "product": "ec2-networking", "role": "Security Group / NACL / Verified Access"},
            {"provider": AWS_PROVIDER, "product": "network-firewall", "role": "托管网络防火墙"},
            {"provider": AWS_PROVIDER, "product": "wafv2", "role": "Web ACL"},
            {"provider": AWS_PROVIDER, "product": "shield", "role": "DDoS 防护"},
            {"provider": AWS_PROVIDER, "product": "fms", "role": "跨账号安全策略"},
        ],
        "keywords": ["SecurityGroup", "NetworkAcl", "Firewall", "WebACL", "Shield", "VerifiedAccess", "Protection"],
        "decisions": [("子网/实例级访问控制", "Security Group / NACL"), ("南北向或东西向 L3/L4 检查", "Network Firewall / GWLB"), ("HTTP/HTTPS L7 防护", "WAF"), ("DDoS 防护", "Shield")],
    },
    {
        "slug": "observability",
        "title": "网络诊断与可视化",
        "description": "流量审计、可达性诊断、拓扑可视化、互联网路径观测。",
        "products": [
            {"provider": ALIYUN_PROVIDER, "product": "nis", "role": "路径分析、抓包、可达性诊断"},
            {"provider": ALIYUN_PROVIDER, "product": "Vpc", "role": "VPC Flow Log"},
            {"provider": AWS_PROVIDER, "product": "ec2-networking", "role": "Flow Logs / Traffic Mirroring / Network Insights"},
            {"provider": AWS_PROVIDER, "product": "networkmonitor", "role": "混合网络路径监控"},
            {"provider": AWS_PROVIDER, "product": "networkflowmonitor", "role": "网络流监控"},
            {"provider": AWS_PROVIDER, "product": "internetmonitor", "role": "公网路径性能观测"},
        ],
        "keywords": ["FlowLog", "PathAnalysis", "Reachability", "Topology", "PacketCapture", "Trace", "NetworkInsights", "Monitor"],
        "decisions": [("为什么不通或丢包", "NIS / Network Insights / Network Monitor"), ("流量审计", "VPC Flow Logs"), ("公网体验下降", "Internet Monitor"), ("工作负载流量可见性", "Network Flow Monitor")],
    },
]
