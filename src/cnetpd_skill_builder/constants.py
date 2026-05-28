"""Shared product and topic definitions for CNetPD-Skill."""

from __future__ import annotations

SKILL_NAME = "CNetPD-Skill"
PROJECT_NAME = "CNetPD-Skill-Builder"
PROJECT_DESCRIPTION = "Cloud Networking PD Skill"

PROVIDER = "aliyun"
PROVIDER_DISPLAY = "Alibaba Cloud"

BASE_URL = "https://api.aliyun.com/meta/v1/"
PRODUCTS_URL = BASE_URL + "products.json"

DATA_SCHEMA_VERSION = 1
DEFAULT_CACHE_DIR = "~/.cache/cnetpd-skill/data"

PRODUCTS: list[dict] = [
    {
        "product": "Vpc",
        "display": "专有网络 VPC",
        "summary": "VPC/子网/路由/EIP/NAT/VPN/IPv6 等核心网络基础设施",
        "coverage": ["隔离网络", "公网访问", "VPN", "IPv6", "子网路由"],
    },
    {
        "product": "Cbn",
        "display": "云企业网 CEN",
        "summary": "多地域 VPC/VBR 内网互联枢纽，支持转发路由器精细路由",
        "coverage": ["跨地域互联", "混合云路由", "流量工程"],
    },
    {
        "product": "Ga",
        "display": "全球加速 GA",
        "summary": "跨地域用户就近接入 + 骨干网加速，公网面的加速产品",
        "coverage": ["跨地域加速", "公网接入", "海外加速"],
    },
    {
        "product": "Slb",
        "display": "传统型负载均衡 CLB",
        "summary": "L4/L7 综合型负载均衡，成熟稳定",
        "coverage": ["负载均衡", "公网接入"],
    },
    {
        "product": "Alb",
        "display": "应用型负载均衡 ALB",
        "summary": "L7 专精：HTTP/HTTPS/HTTP-2/WebSocket/gRPC/QUIC、丰富路由规则",
        "coverage": ["L7 负载均衡", "HTTPS 网关", "流量路由"],
    },
    {
        "product": "Nlb",
        "display": "网络型负载均衡 NLB",
        "summary": "L4 专精：千万并发、低延迟、保留源 IP",
        "coverage": ["L4 负载均衡", "高并发 TCP", "游戏/长连接"],
    },
    {
        "product": "Gwlb",
        "display": "网关型负载均衡 GWLB",
        "summary": "透明流量牵引到第三方/自建安全网关",
        "coverage": ["流量牵引", "网络安全编排"],
    },
    {
        "product": "nis",
        "display": "网络智能服务 NIS",
        "summary": "路径分析、抓包、可达性诊断、拓扑可视化",
        "coverage": ["网络诊断", "可视化", "流量分析"],
    },
    {
        "product": "Privatelink",
        "display": "私网连接 PrivateLink",
        "summary": "服务提供方暴露终端节点，消费方单向私网访问",
        "coverage": ["VPC 间私网", "SaaS 私网接入", "跨账号服务暴露"],
    },
    {
        "product": "ExpressConnectRouter",
        "display": "高速通道路由器 ECR",
        "summary": "多 VBR / 多账号 / 多地域专线路由编排",
        "coverage": ["混合云路由", "跨账号专线"],
    },
    {
        "product": "VpcIpam",
        "display": "VPC IP 地址管理 IPAM",
        "summary": "多 VPC/多账号 CIDR 统一规划、地址池、冲突检测",
        "coverage": ["IP 规划", "地址池", "CIDR 治理"],
    },
    {
        "product": "Eipanycast",
        "display": "任播 EIP",
        "summary": "同一公网 IP 在多地域发布，用户就近接入",
        "coverage": ["任播接入", "全球统一 IP"],
    },
    {
        "product": "VpcPeer",
        "display": "VPC 对等连接",
        "summary": "两两 VPC 直连，小规模互联",
        "coverage": ["VPC 互联"],
    },
]

PRODUCT_CODES = [item["product"] for item in PRODUCTS]

TOPICS: list[dict] = [
    {
        "slug": "public-access",
        "title": "公网访问",
        "description": "VPC 内资源访问公网；公网用户访问 VPC 内服务。",
        "products": [
            {"provider": PROVIDER, "product": "Vpc", "role": "EIP / NAT / IPv6 / 共享带宽"},
            {"provider": PROVIDER, "product": "Slb", "role": "传统公网负载均衡入口"},
            {"provider": PROVIDER, "product": "Alb", "role": "公网 L7 入口"},
            {"provider": PROVIDER, "product": "Nlb", "role": "公网 L4 入口"},
            {"provider": PROVIDER, "product": "Ga", "role": "跨地域公网加速"},
            {"provider": PROVIDER, "product": "Eipanycast", "role": "多地域同一公网 IP"},
        ],
        "keywords": ["EIP", "NAT", "Snat", "Dnat", "Anycast", "Internet", "PublicIp", "公网", "带宽"],
        "decisions": [
            ("单实例出公网", "EIP"),
            ("多实例共享出公网", "NAT Gateway + SNAT"),
            ("多实例暴露 Web 服务", "公网 ALB"),
            ("海外或跨地域用户访问", "GA + 源站负载均衡"),
        ],
    },
    {
        "slug": "load-balancing",
        "title": "负载均衡选型",
        "description": "在多后端实例之间分发流量；新方案优先从 L7/L4/网关型入口判断。",
        "products": [
            {"provider": PROVIDER, "product": "Slb", "role": "传统 L4/L7 兼容"},
            {"provider": PROVIDER, "product": "Alb", "role": "L7、HTTPS、gRPC、内容路由"},
            {"provider": PROVIDER, "product": "Nlb", "role": "L4、高并发、长连接"},
            {"provider": PROVIDER, "product": "Gwlb", "role": "透明流量牵引"},
        ],
        "keywords": ["LoadBalancer", "Listener", "BackendServer", "ServerGroup", "HealthCheck", "Rule"],
        "decisions": [
            ("HTTP/HTTPS/gRPC/内容路由", "ALB"),
            ("TCP/UDP/高并发/长连接", "NLB"),
            ("兼容传统架构", "CLB"),
            ("安全网关透明串联", "GWLB"),
        ],
    },
    {
        "slug": "cross-region",
        "title": "跨地域互联",
        "description": "多地域 VPC 间内网互通，或公网用户跨地域加速接入。",
        "products": [
            {"provider": PROVIDER, "product": "Cbn", "role": "多地域内网互通枢纽"},
            {"provider": PROVIDER, "product": "Ga", "role": "公网面跨地域加速"},
            {"provider": PROVIDER, "product": "Vpc", "role": "承载网络实体"},
        ],
        "keywords": ["CenInstance", "TransitRouter", "Bandwidth", "Accelerator", "CrossBorder", "Region"],
        "decisions": [
            ("VPC 内网跨地域互通", "CEN"),
            ("公网用户跨地域加速", "GA"),
            ("内网互通与公网加速都要", "CEN + GA"),
        ],
    },
    {
        "slug": "hybrid-cloud",
        "title": "混合云接入",
        "description": "本地 IDC、办公网或其他云接入云上 VPC。",
        "products": [
            {"provider": PROVIDER, "product": "Vpc", "role": "VPN Gateway / VBR"},
            {"provider": PROVIDER, "product": "ExpressConnectRouter", "role": "专线路由编排"},
            {"provider": PROVIDER, "product": "Cbn", "role": "统一多地域专线互通"},
        ],
        "keywords": ["VpnGateway", "VpnConnection", "PhysicalConnection", "VirtualBorderRouter", "Bgp"],
        "decisions": [
            ("轻量或临时连接", "VPN Gateway"),
            ("生产级低延迟大带宽", "物理专线 + VBR"),
            ("多账号多地域专线编排", "VBR + ECR + CEN"),
        ],
    },
    {
        "slug": "private-connect",
        "title": "私网打通",
        "description": "VPC 之间或跨账号服务之间的内网连通。",
        "products": [
            {"provider": PROVIDER, "product": "VpcPeer", "role": "少量 VPC 点对点互联"},
            {"provider": PROVIDER, "product": "Cbn", "role": "多 VPC 集线器互联"},
            {"provider": PROVIDER, "product": "Privatelink", "role": "服务级单向私网访问"},
        ],
        "keywords": ["PeerConnection", "VpcEndpoint", "EndpointService", "PrivateLink", "Consumer", "Provider"],
        "decisions": [
            ("2-3 个 VPC 双向互通", "VPC Peer"),
            ("多 VPC 或跨地域互通", "CEN"),
            ("只暴露服务不暴露整张网", "PrivateLink"),
        ],
    },
    {
        "slug": "ip-management",
        "title": "IP 地址管理",
        "description": "IP 资源规划、CIDR 冲突治理、公网 IP 策略。",
        "products": [
            {"provider": PROVIDER, "product": "VpcIpam", "role": "CIDR 统一规划与冲突检测"},
            {"provider": PROVIDER, "product": "Eipanycast", "role": "多地域同一公网 IP"},
            {"provider": PROVIDER, "product": "Vpc", "role": "普通 EIP 与共享带宽"},
        ],
        "keywords": ["Ipam", "IpamPool", "Cidr", "Anycast", "EipAddress", "CommonBandwidthPackage"],
        "decisions": [
            ("普通公网 IP", "EIP"),
            ("多 EIP 共享带宽", "共享带宽包"),
            ("企业级 CIDR 规划", "VPC IPAM"),
            ("多地域统一入口 IP", "Anycast EIP"),
        ],
    },
    {
        "slug": "observability",
        "title": "网络诊断与可视化",
        "description": "流量审计、可达性诊断、拓扑可视化。",
        "products": [
            {"provider": PROVIDER, "product": "nis", "role": "路径分析、抓包、可达性诊断"},
            {"provider": PROVIDER, "product": "Vpc", "role": "VPC Flow Log"},
            {"provider": PROVIDER, "product": "Cbn", "role": "CEN Flow Log"},
        ],
        "keywords": ["FlowLog", "PathAnalysis", "Reachability", "Topology", "PacketCapture", "Trace"],
        "decisions": [
            ("为什么不通或丢包", "NIS 可达性诊断"),
            ("流量审计", "VPC/CEN Flow Log"),
            ("拓扑可视化", "NIS 拓扑"),
        ],
    },
]
