#!/usr/bin/env python3
"""
阿里云网络域 skill 生成器

把 13 个网络产品的单产品数据封装成一个 **aliyun-network-api** 域 skill，
新增 L-1 域层（产品清单 + 跨产品主题），保持渐进披露。

形态：重封装（form A）——内嵌全部 13 产品的 splitter 数据（~14MB）。

用法:
  python build_network_skill.py <splitter_output_dir> [--target <dir>] [--force]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

VERSION = "1.0.0"
logger = logging.getLogger("build_network_skill")

SELF_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# 产品清单（13 个，splitter 输出目录名 → 显示名 + 角色描述）
# ---------------------------------------------------------------------------

PRODUCTS: list[dict] = [
    {"product": "Vpc", "display": "专有网络 VPC",
     "summary": "VPC/子网/路由/EIP/NAT/VPN/IPv6 等核心网络基础设施",
     "coverage": ["隔离网络", "公网访问", "VPN", "IPv6", "子网路由"]},
    {"product": "Cbn", "display": "云企业网 CEN",
     "summary": "多地域 VPC/VBR 内网互联枢纽，支持转发路由器精细路由",
     "coverage": ["跨地域互联", "混合云路由", "流量工程"]},
    {"product": "Ga", "display": "全球加速 GA",
     "summary": "跨地域用户就近接入 + 骨干网加速，公网面的加速产品",
     "coverage": ["跨地域加速", "公网接入", "海外加速"]},
    {"product": "Slb", "display": "传统型负载均衡 CLB",
     "summary": "L4/L7 综合型负载均衡，成熟稳定",
     "coverage": ["负载均衡", "公网接入"]},
    {"product": "Alb", "display": "应用型负载均衡 ALB",
     "summary": "L7 专精：HTTP/HTTPS/HTTP-2/WebSocket/gRPC/QUIC、丰富路由规则",
     "coverage": ["L7 负载均衡", "HTTPS 网关", "流量路由"]},
    {"product": "Nlb", "display": "网络型负载均衡 NLB",
     "summary": "L4 专精：千万并发、低延迟、保留源 IP",
     "coverage": ["L4 负载均衡", "高并发 TCP", "游戏/长连接"]},
    {"product": "Gwlb", "display": "网关型负载均衡 GWLB",
     "summary": "透明流量牵引到第三方/自建安全网关",
     "coverage": ["流量牵引", "网络安全编排"]},
    {"product": "nis", "display": "网络智能服务 NIS",
     "summary": "路径分析、抓包、可达性诊断、拓扑可视化",
     "coverage": ["网络诊断", "可视化", "流量分析"]},
    {"product": "Privatelink", "display": "私网连接 PrivateLink",
     "summary": "服务提供方暴露终端节点，消费方单向私网访问",
     "coverage": ["VPC 间私网", "SaaS 私网接入", "跨账号服务暴露"]},
    {"product": "ExpressConnectRouter", "display": "高速通道路由器 ECR",
     "summary": "多 VBR / 多账号 / 多地域专线路由编排",
     "coverage": ["混合云路由", "跨账号专线"]},
    {"product": "VpcIpam", "display": "VPC IP 地址管理 IPAM",
     "summary": "多 VPC/多账号 CIDR 统一规划、地址池、冲突检测",
     "coverage": ["IP 规划", "地址池", "CIDR 治理"]},
    {"product": "Eipanycast", "display": "任播 EIP",
     "summary": "同一公网 IP 在多地域发布，用户就近接入",
     "coverage": ["任播接入", "全球统一 IP"]},
    {"product": "VpcPeer", "display": "VPC 对等连接",
     "summary": "两两 VPC 直连，小规模互联",
     "coverage": ["VPC 互联"]},
]


# ---------------------------------------------------------------------------
# 7 个主题种子（核心内容；API 级引用由下面的自动扩展补全）
# ---------------------------------------------------------------------------

TOPICS: list[dict] = [
    {
        "slug": "public-access",
        "title": "公网访问（出/入）",
        "description": "VPC 内资源访问公网；公网用户访问 VPC 内服务",
        "products": [
            {"product": "Vpc", "role": "EIP / NAT Gateway (SNAT/DNAT) / IPv6 Gateway / 共享带宽"},
            {"product": "Slb", "role": "公网负载均衡入口（综合型）"},
            {"product": "Alb", "role": "公网 L7 入口"},
            {"product": "Nlb", "role": "公网 L4 入口"},
            {"product": "Ga", "role": "跨地域用户就近接入 + 骨干网加速"},
            {"product": "Eipanycast", "role": "任播 EIP，多地域同一 IP"},
        ],
        "keywords": [
            "EIP", "Eip", "NAT", "Snat", "Dnat", "Anycast",
            "CommonBandwidthPackage", "Ipv6Gateway", "Internet",
            "PublicIp", "Accelerator", "公网", "带宽",
        ],
        "decisions": [
            ("单实例出公网", "EIP 直绑 ECS"),
            ("多实例共享出公网", "NAT Gateway + SNAT"),
            ("单实例暴露服务", "EIP 或 公网 CLB（后端 1 台）"),
            ("多实例暴露服务", "公网 CLB/ALB/NLB（按主题 2 选）"),
            ("端口映射入内网", "NAT Gateway + DNAT"),
            ("海外用户加速访问", "GA（前端）+ 后端 SLB/ECS"),
            ("多地域就近用户接入", "Anycast EIP"),
        ],
        "typical_patterns": [
            "ECS 访问公网：NAT Gateway + EIP（SNAT 条目）",
            "公网用户访问 Web 服务：ALB(公网) + ECS",
            "海外加速：GA + 源站 SLB",
        ],
    },
    {
        "slug": "load-balancing",
        "title": "负载均衡选型（L4/L7/网关）",
        "description": "在多后端实例之间分发流量；新项目默认从 ALB/NLB 选",
        "products": [
            {"product": "Slb", "role": "传统 L4+L7 综合型（CLB），成熟、兼容性好"},
            {"product": "Alb", "role": "L7 专精，HTTP/2/gRPC/QUIC，内容路由"},
            {"product": "Nlb", "role": "L4 专精，千万并发，保留源 IP"},
            {"product": "Gwlb", "role": "网关型，透明流量牵引"},
        ],
        "keywords": [
            "LoadBalancer", "Listener", "BackendServer", "ServerGroup",
            "HealthCheck", "Vserver", "Rule", "Certificate", "AclEntry",
        ],
        "decisions": [
            ("L7 + 内容路由 / HTTPS / gRPC", "ALB"),
            ("L4 + 超高并发 / 游戏 / 长连接", "NLB"),
            ("传统 L4-L7 兼容 / 老架构", "CLB"),
            ("流量牵引到第三方安全网关", "GWLB"),
            ("跨 AZ 多地域入口", "ALB/NLB 原生 + GA 补跨地域"),
        ],
        "typical_patterns": [
            "Web 服务入口：ALB(公网)",
            "游戏/TCP 服务：NLB",
            "透明防火墙：GWLB + 第三方网关 ECS",
        ],
    },
    {
        "slug": "cross-region",
        "title": "跨地域互联",
        "description": "多地域 VPC 间内网互通 / 用户跨地域公网接入",
        "products": [
            {"product": "Cbn", "role": "CEN：多地域/多实例内网互通枢纽"},
            {"product": "Ga", "role": "全球加速：公网面跨地域加速"},
            {"product": "Vpc", "role": "被连接的网络实体"},
        ],
        "keywords": [
            "CenInstance", "TransitRouter", "Bandwidth", "CenRouteEntry",
            "Accelerator", "CrossBorder", "GeoRoute", "Region",
        ],
        "decisions": [
            ("多 VPC 内网互通（同/跨地域）", "CEN"),
            ("多地域路由控制 / 策略 / 带宽包", "CEN + 转发路由器 TR"),
            ("公网用户跨地域加速", "GA"),
            ("内网互通 + 公网加速同时", "CEN（内网）+ GA（公网），互补"),
        ],
        "typical_patterns": [
            "多地域 VPC 全互联：CEN + 带宽包",
            "海外用户访问国内服务：GA + 源站 SLB",
        ],
    },
    {
        "slug": "hybrid-cloud",
        "title": "混合云接入",
        "description": "本地 IDC / 办公网 / 其他云 → 阿里云 VPC 的接入方式",
        "products": [
            {"product": "Vpc", "role": "VPN Gateway (IPsec/SSL/IPsec-Server)、VBR（专线云侧终结）"},
            {"product": "ExpressConnectRouter", "role": "多 VBR/多账号/多地域专线路由编排"},
            {"product": "Cbn", "role": "把 VBR 挂进 CEN，统一多地域"},
        ],
        "keywords": [
            "VpnGateway", "VpnConnection", "CustomerGateway", "IpsecServer",
            "SslVpnServer", "SslVpnClient", "PhysicalConnection",
            "VirtualBorderRouter", "ExpressConnect", "Bgp",
        ],
        "decisions": [
            ("轻量 / 小带宽 / 临时", "VPN Gateway (IPsec)"),
            ("远程办公接入", "SSL-VPN / IPsec-Server"),
            ("生产级 / 稳定低延迟 / 大带宽", "物理专线 + VBR"),
            ("多地域/多账号专线编排", "物理专线 + VBR + ECR"),
            ("专线故障应急备份", "专线 + VPN 并联"),
        ],
        "typical_patterns": [
            "IDC 接云：物理专线 → VBR → VPC",
            "多地域 IDC 接云：多 VBR + ECR 统一路由",
            "应急备份：专线 + VPN Gateway",
        ],
    },
    {
        "slug": "private-connect",
        "title": "VPC 间 / 服务间私网打通",
        "description": "VPC 之间或跨账号的内网连通（不走公网）",
        "products": [
            {"product": "VpcPeer", "role": "两两 VPC 直连"},
            {"product": "Cbn", "role": "多 VPC 全互联（集线器模型）"},
            {"product": "Privatelink", "role": "服务级私网访问（单向），不暴露整张网"},
        ],
        "keywords": [
            "PeerConnection", "VpcPeer", "VpcEndpoint", "EndpointService",
            "CenInstance", "PrivateLink", "Consumer", "Provider",
        ],
        "decisions": [
            ("2-3 个 VPC 全互联", "VpcPeer（点对点，简单）"),
            ("多 VPC / 多地域全互联", "CEN（集线器）"),
            ("跨账号访问某个服务但不想暴露整张网", "PrivateLink"),
            ("SaaS 供应商对客户暴露服务", "PrivateLink"),
            ("需要双向互通", "VpcPeer 或 CEN"),
        ],
        "typical_patterns": [
            "双 VPC 互通：VpcPeer",
            "多 VPC 互联：CEN",
            "跨账号服务消费：PrivateLink 终端节点",
        ],
    },
    {
        "slug": "ip-management",
        "title": "IP 地址管理",
        "description": "IP 资源规划、避免 CIDR 冲突、公网 IP 策略",
        "products": [
            {"product": "VpcIpam", "role": "多 VPC / 多账号 CIDR 统一规划、地址池、冲突检测"},
            {"product": "Eipanycast", "role": "任播 EIP，多地域同一 IP"},
            {"product": "Vpc", "role": "普通 EIP、共享带宽包"},
        ],
        "keywords": [
            "Ipam", "IpamPool", "IpamScope", "Cidr",
            "Anycast", "EipAddress", "CommonBandwidthPackage",
        ],
        "decisions": [
            ("普通公网 IP", "EIP（在 Vpc 内）"),
            ("多 EIP 共享出口带宽", "共享带宽包（在 Vpc 内）"),
            ("多地域共享同一公网 IP（用户无感跨地域）", "Anycast EIP"),
            ("多 VPC 地址规划 / 防冲突", "VPC IPAM"),
            ("50+ VPC 的企业级 IP 治理", "VPC IPAM 必备"),
        ],
        "typical_patterns": [
            "企业级 IP 规划：IPAM 池 → VPC CIDR 分配",
            "全球单一入口 IP：Anycast EIP + 后端各地域 SLB",
        ],
    },
    {
        "slug": "observability",
        "title": "网络可视化与诊断",
        "description": "流量审计、可达性诊断、拓扑可视化",
        "products": [
            {"product": "nis", "role": "NIS：路径分析、抓包、可达性诊断、拓扑图"},
            {"product": "Vpc", "role": "VPC Flow Log"},
            {"product": "Cbn", "role": "CEN Flow Log"},
        ],
        "keywords": [
            "FlowLog", "PathAnalysis", "Reachability", "Topology",
            "PacketCapture", "NetworkDiagnosis", "Trace",
        ],
        "decisions": [
            ("为什么不通 / 丢包排查", "NIS 可达性诊断"),
            ("端到端路径分析", "NIS 路径分析"),
            ("流量审计 / 安全合规", "VPC Flow Log"),
            ("跨地域 / CEN 流量分析", "CEN Flow Log"),
            ("网络拓扑可视化", "NIS 拓扑图"),
        ],
        "typical_patterns": [
            "排障：NIS 诊断 + VPC FlowLog 佐证",
            "合规审计：VPC/CEN FlowLog 全量采集",
        ],
    },
]


# ---------------------------------------------------------------------------
# 域 skill SKILL.md 模板
# ---------------------------------------------------------------------------


SKILL_MD_TEMPLATE = """---
name: aliyun-network-api
description: |
  阿里云网络产品域能力与机制认知 skill，覆盖 13 个网络基础设施产品（不含 CDN 和 DNS）：{products_csv}。
  面向 AI PRD 设计场景，聚焦"做 X 方案该用哪些产品组合"的跨产品能力地图。
  通过 {topic_count} 个业务主题（{topic_titles_csv}）导航到具体产品与能力。
  典型触发：阿里云网络规划、VPC/SLB/CEN 组网方案、混合云接入、跨地域互联、负载均衡选型、公网访问方案、私网打通、IP 地址治理、网络可视化与诊断；
  当用户抽象地问"阿里云网络这块怎么设计/选型/组合"时应优先使用本 skill；
  当用户聚焦单一产品的深度细节时（例如"VPC 的 CreateSnatEntry 错误码"），可使用对应单产品 skill。
---

# 阿里云网络域 skill

## 定位

面向 **AI PRD 设计**，提供阿里云网络基础设施的**跨产品能力地图**。本 skill 的核心价值在于把 13 个产品编织进 {topic_count} 个业务主题——当用户问"做 X 场景用什么"时，直接从主题切入，而不是逐个查产品。

**与单产品 skill 的分工**：
- 本 skill：跨产品选型、能力组合、方案级 PRD 场景
- 单产品 skill（aliyun-vpc-api、aliyun-slb-api 等）：单产品内的能力细节与契约

## 渐进披露层次

```
L-1  域入口       ~{l_minus_1_kb} KB    13 产品 + {topic_count} 个业务主题
 ↓   (按主题/产品定位)
L0   产品索引     ~5 KB     data/<Product>/index.json
 ↓
L1   分区详情     ~10-25 KB  data/<Product>/groups/<slug>.json
 ↓
L2   API 契约     ~10-30 KB  data/<Product>/apis/<Api>.json
```

## 查询工具

```bash
SCRIPT="<本skill目录>/scripts/query.py"

# L-1 域层
python3 $SCRIPT domain                     # 13 产品 + 7 主题全貌
python3 $SCRIPT products                   # 只看产品清单
python3 $SCRIPT topics                     # 只看主题清单
python3 $SCRIPT topic <slug>               # 展开某主题（候选产品 / 选型 / 组合）

# L0/L1/L2 产品内查询（需 --product）
python3 $SCRIPT product <slug>             # 等价某产品的 capabilities
python3 $SCRIPT group <slug> --product <p> # 某产品某分区
python3 $SCRIPT detail <Api> --product <p> # 某能力完整契约
python3 $SCRIPT constraints <Api> --product <p>
python3 $SCRIPT deprecated --product <p>

# 跨产品搜索（无 --product 时扫所有产品）
python3 $SCRIPT search "<关键词>"
python3 $SCRIPT search "<关键词>" --product <p>   # 限定单产品
```

## 7 个业务主题（入口）

{topic_overview_table}

详见 `references/network-topics.md` 的完整选型决策表与典型组合。

## 13 个产品（入口）

{product_table}

## 回答 PRD 问题的规范

面对一个跨产品的 PRD 需求，Agent 应当：

1. **先回主题**：从 7 个业务主题中定位用户需求落在哪类（公网访问？负载均衡？跨地域？混合云？…）
2. **给出产品组合**：从该主题的"候选产品"中挑选，说明选型依据
3. **下钻单产品能力**：对每个选中的产品，用 `product <slug>` 或 `group … --product …` 查具体能力
4. **绘制依赖链**：说明哪个产品的哪个能力输出，被哪个产品消费（调用顺序）
5. **标注非功能属性**：异步/同步、配额、计费、废弃状态

**不要**贴大段 JSON 给用户，**不要**把跨产品的方案写成"调用 13 个 API"的流水账。

## 数据层级对照

| 层级 | 内容 | 文件 |
|---|---|---|
| L-1 域 | 产品清单 + 主题 | `data/_network-index.json` |
| L0 产品 | 能力分区骨架 | `data/<Product>/index.json` |
| L1 分区 | 能力签名摘要 | `data/<Product>/groups/<slug>.json` |
| L2 API | 完整契约 | `data/<Product>/apis/<Api>.json` |
"""


# ---------------------------------------------------------------------------
# 自动扩展：为每个主题从各产品 API 中匹配关键词，填充 relevantApis
# ---------------------------------------------------------------------------


def expand_topic_apis(
    topic: dict, data_dir: Path, max_per_product: int = 8
) -> dict:
    """为主题填充 relevantApis: 各产品里按关键词匹配的 API 列表"""
    result_by_product: dict[str, list[dict]] = {}

    keywords_lower = [kw.lower() for kw in topic.get("keywords", [])]
    if not keywords_lower:
        return {}

    for ref in topic.get("products", []):
        product = ref["product"]
        product_dir = data_dir / product / "groups"
        if not product_dir.exists():
            continue

        matches: list[dict] = []
        for gfile in sorted(product_dir.glob("*.json")):
            try:
                group = json.loads(gfile.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            for api in group.get("apis", []):
                name = api.get("name", "")
                summary = api.get("summary", "")
                hay = f"{name} {summary}".lower()
                if any(kw in hay for kw in keywords_lower):
                    matches.append({
                        "api": name,
                        "group": group.get("group", gfile.stem),
                        "summary": summary,
                    })
                    if len(matches) >= max_per_product:
                        break
            if len(matches) >= max_per_product:
                break

        if matches:
            result_by_product[product] = matches

    return result_by_product


# ---------------------------------------------------------------------------
# L-1 域索引 & SKILL.md & network-topics.md
# ---------------------------------------------------------------------------


def build_domain_index(
    data_dir: Path,
    product_meta: list[dict],
    topics: list[dict],
) -> dict:
    # 汇总产品 API 计数
    products: list[dict] = []
    for meta in product_meta:
        idx_file = data_dir / meta["product"] / "index.json"
        api_count = 0
        group_count = 0
        if idx_file.exists():
            try:
                idx = json.loads(idx_file.read_text(encoding="utf-8"))
                api_count = idx.get("totalApis", 0)
                group_count = len(idx.get("groups", []))
            except json.JSONDecodeError:
                pass
        products.append({
            "product": meta["product"],
            "slug": meta["product"].lower(),
            "display": meta["display"],
            "summary": meta["summary"],
            "coverage": meta["coverage"],
            "apiCount": api_count,
            "groupCount": group_count,
        })

    # 扩展主题（加 relevantApis）
    expanded_topics: list[dict] = []
    for topic in topics:
        relevant = expand_topic_apis(topic, data_dir)
        expanded = {
            "slug": topic["slug"],
            "title": topic["title"],
            "description": topic["description"],
            "products": topic["products"],
            "decisions": [{"when": w, "use": u} for w, u in topic["decisions"]],
            "typicalPatterns": topic["typical_patterns"],
        }
        if relevant:
            expanded["relevantApis"] = relevant
        expanded_topics.append(expanded)

    return {
        "_layer": "L-1",
        "_version": VERSION,
        "domain": "aliyun-network",
        "description": "阿里云网络基础设施产品域（排除 CDN 和 DNS）",
        "productCount": len(products),
        "topicCount": len(expanded_topics),
        "products": products,
        "topics": expanded_topics,
    }


def render_skill_md(index: dict) -> str:
    products = index["products"]
    topics = index["topics"]

    products_csv = "、".join(p["display"] for p in products)
    topic_titles_csv = "、".join(t["title"] for t in topics)

    topic_rows = []
    for t in topics:
        prods = "、".join(p["product"] for p in t["products"])
        topic_rows.append(f"| `{t['slug']}` | {t['title']} | {prods} |")
    topic_overview_table = (
        "| Slug | 主题 | 涉及产品 |\n"
        "|---|---|---|\n"
        + "\n".join(topic_rows)
    )

    product_rows = []
    for p in products:
        cov = "、".join(p["coverage"])
        product_rows.append(
            f"| `{p['slug']}` | {p['display']} | {p['apiCount']} | {cov} |"
        )
    product_table = (
        "| Slug | 产品 | API 数 | 覆盖能力 |\n"
        "|---|---|---:|---|\n"
        + "\n".join(product_rows)
    )

    # 预估 L-1 大小
    l_minus_1_bytes = len(json.dumps(index, ensure_ascii=False, indent=2).encode("utf-8"))
    l_minus_1_kb = max(1, l_minus_1_bytes // 1024)

    return SKILL_MD_TEMPLATE.format(
        products_csv=products_csv,
        topic_count=len(topics),
        topic_titles_csv=topic_titles_csv,
        l_minus_1_kb=l_minus_1_kb,
        topic_overview_table=topic_overview_table,
        product_table=product_table,
    )


def render_topics_md(index: dict) -> str:
    """把 topics 渲染成人类可读的 references/network-topics.md"""
    lines = [
        "# 阿里云网络域业务主题",
        "",
        "本文档展开 L-1 域索引里的 7 个业务主题。PRD 设计时按主题入口快速定位候选产品组合。",
        "",
    ]
    for t in index["topics"]:
        lines.append(f"## {t['title']}（`{t['slug']}`）")
        lines.append("")
        lines.append(f"**场景**：{t['description']}")
        lines.append("")

        lines.append("**候选产品与角色**：")
        for p in t["products"]:
            lines.append(f"- **{p['product']}** — {p['role']}")
        lines.append("")

        lines.append("**选型决策**：")
        lines.append("")
        lines.append("| 当 | 选 |")
        lines.append("|---|---|")
        for d in t["decisions"]:
            lines.append(f"| {d['when']} | {d['use']} |")
        lines.append("")

        lines.append("**典型组合**：")
        for p in t["typicalPatterns"]:
            lines.append(f"- {p}")
        lines.append("")

        relevant = t.get("relevantApis", {})
        if relevant:
            lines.append("**相关 API（关键词自动匹配，仅供入口参考）**：")
            for product, apis in relevant.items():
                names = ", ".join(f"`{a['api']}`" for a in apis[:5])
                more = f"（共 {len(apis)} 个匹配）" if len(apis) > 5 else ""
                lines.append(f"- {product}: {names}{more}")
            lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# query.py（domain-aware）— 生成到 skill 的 scripts 目录
# ---------------------------------------------------------------------------


DOMAIN_QUERY_PY = '''#!/usr/bin/env python3
"""
阿里云网络域 skill 查询工具（domain-aware）

命令:
  domain                              L-1 域层：13 产品 + 7 主题全貌
  products                            产品清单
  topics                              主题清单
  topic <slug>                        展开某主题
  product <slug>                      等价于某产品的 capabilities
  group <slug> --product <p>          某产品某分区
  search <kw> [--product <p>]         跨产品/单产品搜索
  detail <Api> --product <p> [--full] 某能力完整契约
  constraints <Api> --product <p>     约束边界
  deprecated --product <p>            单产品废弃能力
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

DATA_ROOT = Path(os.environ.get(
    "ALIYUN_NETWORK_DATA",
    Path(__file__).resolve().parent.parent / "data"
))


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _index() -> dict:
    return _load(DATA_ROOT / "_network-index.json")


def _product_dir(slug_or_name: str) -> Path | None:
    """产品 slug/name → data/<Product>/，不区分大小写"""
    if not DATA_ROOT.exists():
        return None
    needle = slug_or_name.lower()
    for d in DATA_ROOT.iterdir():
        if d.is_dir() and d.name.lower() == needle:
            return d
    return None


_CONSTRAINT_CATEGORIES = {
    "ResourceNotFound": "资源不存在", "IncorrectStatus": "资源状态不满足",
    "IncorrectBusinessStatus": "商业状态不满足", "ResourceAlreadyExist": "资源已存在",
    "QuotaExceeded": "配额超限", "OperationFailed": "操作失败",
    "OperationDenied": "操作被拒绝", "UnsupportedRegion": "地域不支持",
    "Forbidden": "权限不足", "InvalidParam": "参数无效", "IllegalParam": "参数非法",
    "InvalidInstanceIds": "实例 ID 无效", "InvalidInstanceType": "实例类型无效",
    "InvalidTagKey": "标签键无效", "NumberExceed": "数量超限",
    "BothEmpty": "必填组合缺失", "MissingParameter": "缺少必填参数",
}


def _classify_error(code: str) -> str:
    prefix = code.split(".")[0] if "." in code else code
    return _CONSTRAINT_CATEGORIES.get(prefix, prefix)


# ---------- domain / products / topics ----------


def cmd_domain() -> None:
    idx = _index()
    print(f"域: {idx['domain']}  —  {idx['description']}")
    print(f"产品: {idx['productCount']} 个  |  主题: {idx['topicCount']} 个\\n")

    print("【产品清单】")
    print(f"{'Slug':<24} {'产品':<26} {'API数':>6}  覆盖")
    print("-" * 90)
    for p in idx["products"]:
        cov = "、".join(p["coverage"][:4])
        print(f"{p['slug']:<24} {p['display']:<26} {p['apiCount']:>6}  {cov}")

    print("\\n【业务主题】")
    for t in idx["topics"]:
        prods = "、".join(r["product"] for r in t["products"])
        print(f"  {t['slug']:<18} {t['title']}")
        print(f"      产品: {prods}")


def cmd_products() -> None:
    for p in _index()["products"]:
        cov = "、".join(p["coverage"][:4])
        print(f"{p['slug']:<24} {p['display']:<26} {p['apiCount']:>6} APIs  {cov}")


def cmd_topics() -> None:
    for t in _index()["topics"]:
        prods = "、".join(r["product"] for r in t["products"])
        print(f"{t['slug']:<18} {t['title']}")
        print(f"  {t['description']}")
        print(f"  产品: {prods}\\n")


def cmd_topic(slug: str) -> None:
    idx = _index()
    topic = next((t for t in idx["topics"] if t["slug"] == slug), None)
    if not topic:
        print(f"未找到主题 '{slug}'。可用: {', '.join(t['slug'] for t in idx['topics'])}")
        return

    print(f"【{topic['title']}】 ({topic['slug']})")
    print(f"\\n{topic['description']}\\n")

    print("候选产品:")
    for p in topic["products"]:
        print(f"  {p['product']:<24} {p['role']}")

    print("\\n选型决策:")
    for d in topic["decisions"]:
        print(f"  - 当 {d['when']}  →  {d['use']}")

    print("\\n典型组合:")
    for p in topic["typicalPatterns"]:
        print(f"  - {p}")

    relevant = topic.get("relevantApis", {})
    if relevant:
        print("\\n相关 API (关键词自动匹配):")
        for product, apis in relevant.items():
            names = ", ".join(a["api"] for a in apis[:8])
            more = f" …共 {len(apis)} 个" if len(apis) > 8 else ""
            print(f"  {product}: {names}{more}")


# ---------- product / group / search / detail / constraints / deprecated ----------


def cmd_product(slug: str) -> None:
    pd = _product_dir(slug)
    if not pd:
        print(f"未找到产品 '{slug}'。查看 products。")
        return
    idx = _load(pd / "index.json")
    product = idx.get("product", slug)
    total = idx.get("totalApis", "?")
    groups = idx.get("groups", [])
    print(f"产品: {product}  |  {total} APIs  |  {len(groups)} 个能力分区\\n")
    print(f"{'Slug':<24} {'能力分区':<20} {'API数':>5}")
    print("-" * 54)
    for g in groups:
        print(f"{g['slug']:<24} {g['title']:<20} {g['count']:>5}")


def cmd_group(slug: str, product: str) -> None:
    pd = _product_dir(product)
    if not pd:
        print(f"未找到产品 '{product}'")
        return
    gfile = pd / "groups" / f"{slug}.json"
    if not gfile.exists():
        print(f"未找到分区 '{slug}' in {product}")
        return
    g = _load(gfile)
    print(f"【{g['title']}】({slug}) in {product} — {len(g['apis'])} 个能力\\n")
    for api in g["apis"]:
        op = f" [{api.get('operationType','')}]" if api.get("operationType") else ""
        dep = " ⚠" if api.get("deprecated") else ""
        print(f"  {api['name']}{op}{dep}")
        print(f"    {api.get('summary','')}")
        if api.get("required"):
            print(f"    必填: {', '.join(api['required'])}")
        if api.get("returns"):
            ret = api["returns"][:8]
            more = " …" if len(api["returns"]) > 8 else ""
            print(f"    返回: {', '.join(ret)}{more}")
        print()


def cmd_search(keyword: str, product: str | None = None) -> None:
    kw = keyword.lower()
    dirs = [_product_dir(product)] if product else [
        d for d in DATA_ROOT.iterdir() if d.is_dir() and (d / "index.json").exists()
    ]
    total = 0
    for pd in dirs:
        if not pd:
            continue
        hits = []
        for gfile in sorted((pd / "groups").glob("*.json")):
            try:
                g = _load(gfile)
            except json.JSONDecodeError:
                continue
            for api in g.get("apis", []):
                hay = f"{api.get('name','')} {api.get('summary','')}".lower()
                if kw in hay:
                    hits.append((g.get("group", gfile.stem), api))
        if hits:
            print(f"\\n【{pd.name}】({len(hits)} matches)")
            for group, api in hits[:15]:
                op = f" [{api.get('operationType','')}]" if api.get("operationType") else ""
                print(f"  {api['name']}{op}  ({group})")
                print(f"    {api.get('summary','')}")
            if len(hits) > 15:
                print(f"  … 省略 {len(hits) - 15}")
            total += len(hits)
    if total == 0:
        print(f"未找到 '{keyword}'")


def _print_param(p: dict) -> None:
    name = p.get("name", "")
    typ = p.get("type", "")
    in_loc = p.get("in", "")
    loc = f" ({in_loc})" if in_loc and in_loc not in ("query", "") else ""
    enum = p.get("enum")
    enum_str = f" ∈ {{{', '.join(str(e) for e in enum[:5])}}}" if enum else ""
    default = p.get("default")
    default_str = f" = {default}" if default is not None else ""
    print(f"  {name}: {typ}{loc}{enum_str}{default_str}")
    if p.get("desc"):
        print(f"      {p['desc']}")


def _is_required(schema: dict) -> bool:
    val = schema.get("required", False)
    if isinstance(val, str):
        return val.lower() == "true"
    return bool(val)


def _param_view(name: str, schema: dict, in_loc: str = "") -> dict:
    desc = schema.get("description", "") or ""
    desc = re.sub(r"\\[([^\\]]*)\\]\\(~~\\d+~~\\)", r"\\1", desc)
    desc = re.sub(r"\\(~~\\d+~~\\)", "", desc)
    first = desc.split("\\n")[0].strip()
    if len(first) > 80:
        first = first[:77] + "..."
    view = {"name": name, "type": schema.get("type", "string")}
    if in_loc:
        view["in"] = in_loc
    if schema.get("format"):
        view["format"] = schema["format"]
    enum_titles = schema.get("enumValueTitles")
    if enum_titles:
        view["enum"] = list(enum_titles.keys())
    elif isinstance(schema.get("enum"), list) and len(schema["enum"]) <= 10:
        view["enum"] = schema["enum"]
    if "default" in schema:
        view["default"] = schema["default"]
    if first:
        view["desc"] = first
    return view


def cmd_detail(api_name: str, product: str, full: bool = False) -> None:
    pd = _product_dir(product)
    if not pd:
        print(f"未找到产品 '{product}'")
        return
    afile = pd / "apis" / f"{api_name}.json"
    if not afile.exists():
        cand = [f.stem for f in (pd / "apis").glob("*.json") if api_name.lower() in f.stem.lower()]
        if cand:
            print(f"未找到 '{api_name}'。候选: {', '.join(cand[:10])}")
        else:
            print(f"未找到 '{api_name}' in {product}")
        return
    api = _load(afile)

    print(f"能力: {api.get('api', api_name)}  (产品: {product})")
    print(f"分区: {api.get('group','')}")
    print(f"标题: {api.get('title','')}")
    if api.get("operationType"):
        print(f"操作类型: {api['operationType']}")
    if api.get("deprecated"):
        print("状态: ⚠ 已废弃")

    desc = api.get("description", "")
    if desc:
        lines = [ln for ln in desc.split("\\n") if ln.strip()]
        print("\\n语义说明:")
        for ln in lines[:8]:
            print(f"  {ln.strip()}")
        if len(lines) > 8 and not full:
            print(f"  …（--full 查看全部 {len(lines)} 行）")

    params = api.get("parameters", [])
    req, opt = [], []
    for p in params:
        schema = p.get("schema", {})
        if not isinstance(schema, dict):
            continue
        if p.get("in") == "body" and schema.get("type") == "object":
            for fn, fs in schema.get("properties", {}).items():
                if not isinstance(fs, dict):
                    continue
                view = _param_view(fn, fs, "body")
                (req if _is_required(fs) else opt).append(view)
            continue
        view = _param_view(p.get("name", ""), schema, p.get("in", ""))
        (req if _is_required(schema) else opt).append(view)

    if req:
        print(f"\\n输入契约（必填，{len(req)}）:")
        for p in req:
            _print_param(p)
    if opt:
        print(f"\\n行为开关（可选，{len(opt)}）:")
        for p in opt[:15]:
            _print_param(p)
        if len(opt) > 15:
            print(f"  …省略 {len(opt)-15}")

    responses = api.get("responses", {})
    top_fields: list[tuple[str, str]] = []
    seen: set[str] = set()
    for code, resp in responses.items():
        schema = resp.get("schema", {})
        if isinstance(schema, dict):
            for name, fs in schema.get("properties", {}).items():
                if name in seen or name == "RequestId":
                    continue
                seen.add(name)
                typ = fs.get("type", "object") if isinstance(fs, dict) else "?"
                top_fields.append((name, typ))
    if top_fields:
        print("\\n返回模型:")
        for n, t in top_fields:
            print(f"  {n}: {t}")

    err = api.get("errorCodes", {})
    if err:
        grouped = defaultdict(list)
        for status, errs in err.items():
            if not isinstance(errs, list):
                continue
            for e in errs:
                c = e.get("errorCode", "") if isinstance(e, dict) else str(e)
                if c:
                    grouped[_classify_error(c)].append(c)
        total = sum(len(v) for v in grouped.values())
        print(f"\\n约束边界（{total} 错误码）:")
        for cat, codes in sorted(grouped.items()):
            print(f"  {cat}: {len(codes)}")
            if full:
                for c in codes[:5]:
                    print(f"    - {c}")


def cmd_constraints(api_name: str, product: str) -> None:
    pd = _product_dir(product)
    if not pd:
        print(f"未找到产品 '{product}'")
        return
    afile = pd / "apis" / f"{api_name}.json"
    if not afile.exists():
        print(f"未找到 '{api_name}' in {product}")
        return
    api = _load(afile)
    err = api.get("errorCodes", {})
    if not err:
        print(f"{api_name} 未声明错误码")
        return
    grouped = defaultdict(list)
    for status, errs in err.items():
        if not isinstance(errs, list):
            continue
        for e in errs:
            c = e.get("errorCode", "") if isinstance(e, dict) else str(e)
            if c:
                grouped[_classify_error(c)].append(c)
    total = sum(len(v) for v in grouped.values())
    print(f"【{api_name}】({product}) 约束边界 — {total} 错误码\\n")
    for cat, codes in sorted(grouped.items(), key=lambda x: -len(x[1])):
        print(f"{cat} ({len(codes)}):")
        for c in codes:
            print(f"  {c}")
        print()


def cmd_deprecated(product: str) -> None:
    pd = _product_dir(product)
    if not pd:
        print(f"未找到产品 '{product}'")
        return
    items = []
    for af in sorted((pd / "apis").glob("*.json")):
        try:
            api = _load(af)
        except json.JSONDecodeError:
            continue
        if api.get("deprecated"):
            items.append((api.get("api", ""), api.get("title", ""), api.get("group", "")))
    if not items:
        print(f"{product} 未标记任何废弃能力")
        return
    by_group = defaultdict(list)
    for n, t, g in items:
        by_group[g].append((n, t))
    print(f"{product} 废弃能力 — {len(items)} 个\\n")
    for g, xs in sorted(by_group.items()):
        print(f"【{g}】({len(xs)})")
        for n, t in xs:
            print(f"  {n} — {t}")
        print()


# ---------- CLI ----------


def main():
    p = argparse.ArgumentParser(description="阿里云网络域 skill 查询工具")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("domain")
    sub.add_parser("products")
    sub.add_parser("topics")

    pt = sub.add_parser("topic"); pt.add_argument("slug")
    pp = sub.add_parser("product"); pp.add_argument("slug")

    pg = sub.add_parser("group")
    pg.add_argument("slug"); pg.add_argument("--product", required=True)

    ps = sub.add_parser("search")
    ps.add_argument("keyword"); ps.add_argument("--product", default=None)

    pd = sub.add_parser("detail")
    pd.add_argument("api_name"); pd.add_argument("--product", required=True)
    pd.add_argument("--full", action="store_true")

    pc = sub.add_parser("constraints")
    pc.add_argument("api_name"); pc.add_argument("--product", required=True)

    pdep = sub.add_parser("deprecated")
    pdep.add_argument("--product", required=True)

    args = p.parse_args()
    if not args.command:
        p.print_help(); sys.exit(0)

    if not DATA_ROOT.exists():
        print(f"错误: 数据目录不存在: {DATA_ROOT}", file=sys.stderr)
        sys.exit(1)

    dispatch = {
        "domain": lambda: cmd_domain(),
        "products": lambda: cmd_products(),
        "topics": lambda: cmd_topics(),
        "topic": lambda: cmd_topic(args.slug),
        "product": lambda: cmd_product(args.slug),
        "group": lambda: cmd_group(args.slug, args.product),
        "search": lambda: cmd_search(args.keyword, args.product),
        "detail": lambda: cmd_detail(args.api_name, args.product, full=args.full),
        "constraints": lambda: cmd_constraints(args.api_name, args.product),
        "deprecated": lambda: cmd_deprecated(args.product),
    }
    dispatch[args.command]()


if __name__ == "__main__":
    main()
'''


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def build(source_dir: Path, target_dir: Path, *, force: bool = False) -> dict:
    if target_dir.exists():
        if not force:
            raise SystemExit(f"{target_dir} 已存在。用 --force 覆盖。")
        shutil.rmtree(target_dir)

    target_dir.mkdir(parents=True)
    (target_dir / "scripts").mkdir()
    (target_dir / "references").mkdir()
    data_dir = target_dir / "data"
    data_dir.mkdir()

    # 拷贝 13 产品数据
    missing = []
    copied = []
    for meta in PRODUCTS:
        src = source_dir / meta["product"]
        if not src.exists():
            missing.append(meta["product"])
            continue
        dst = data_dir / meta["product"]
        shutil.copytree(src, dst)
        copied.append(meta["product"])
        logger.info("拷贝数据: %s", meta["product"])

    if missing:
        logger.warning("缺少以下产品的 splitter 数据: %s", missing)

    # 构建 L-1 域索引（含自动扩展主题 API）
    index = build_domain_index(data_dir, PRODUCTS, TOPICS)
    idx_path = data_dir / "_network-index.json"
    idx_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # SKILL.md
    (target_dir / "SKILL.md").write_text(render_skill_md(index), encoding="utf-8")

    # references
    (target_dir / "references" / "network-topics.md").write_text(
        render_topics_md(index), encoding="utf-8"
    )

    # query.py
    query_path = target_dir / "scripts" / "query.py"
    query_path.write_text(DOMAIN_QUERY_PY, encoding="utf-8")
    query_path.chmod(0o755)

    return {
        "products_copied": len(copied),
        "products_missing": len(missing),
        "index_bytes": idx_path.stat().st_size,
        "topics_count": len(index["topics"]),
        "missing_products": missing,
    }


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
    ))
    logger.setLevel(level)
    logger.addHandler(handler)


def main():
    parser = argparse.ArgumentParser(description="阿里云网络域 skill 生成器")
    parser.add_argument("source_dir", type=Path, help="splitter 输出目录")
    parser.add_argument("--target", "-t", type=Path,
                        default=SELF_DIR / "skills" / "aliyun-network-api",
                        help="skill 输出路径（默认 skills/aliyun-network-api/）")
    parser.add_argument("--force", "-f", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    args = parser.parse_args()
    setup_logging(args.verbose)

    if not args.source_dir.is_dir():
        raise SystemExit(f"源目录不存在: {args.source_dir}")

    t0 = time.time()
    result = build(args.source_dir, args.target, force=args.force)
    elapsed = time.time() - t0

    print("\n" + "=" * 60)
    print(f"  网络域 skill 构建完成 ({elapsed:.1f}s)")
    print("=" * 60)
    print(f"  输出: {args.target}")
    print(f"  产品拷贝: {result['products_copied']}")
    print(f"  产品缺失: {result['products_missing']}")
    if result["missing_products"]:
        print(f"    {result['missing_products']}")
    print(f"  L-1 索引: {result['index_bytes'] / 1024:.1f} KB")
    print(f"  主题数量: {result['topics_count']}")


if __name__ == "__main__":
    main()
