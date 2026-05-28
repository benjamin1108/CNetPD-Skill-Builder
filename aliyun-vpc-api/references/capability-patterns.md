# VPC 能力依赖模式（PRD 设计参考）

当一个产品需求要落到 VPC 上，很少只用单一能力就能实现——典型场景都涉及多个能力按固定顺序组合。本文档列出这些**能力依赖链**，供 PRD 设计阶段判断：

- 要实现 X 场景，会依赖哪些底层能力（能力组合）
- 这些能力的编排顺序（依赖前置）
- 链路中的关键契约传递（前一步的返回字段如何成为后一步的输入）
- 各环节的非功能特性（异步性、前置状态、配额）

这些不是"调用顺序清单"，而是用于理解产品模型的能力拓扑。

## 1. 从零创建 VPC 网络环境

典型顺序：创建 VPC → 创建交换机 → 创建路由条目

```
CreateVpc (RegionId, CidrBlock)
  ↓ 返回 VpcId, VRouterId, RouteTableId
CreateVSwitch (ZoneId, VpcId, CidrBlock)
  ↓ 返回 VSwitchId
CreateRouteEntry (RouteTableId, DestinationCidrBlock, NextHopId)
```

注意：
- CreateVpc 是异步接口，需要轮询 DescribeVpcAttribute 等待状态变为 Created
- CidrBlock 推荐使用 RFC 1918 私有地址，如 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
- 每个 VPC 下的交换机需在不同可用区，网段不能重叠

## 2. NAT 网关 + SNAT 配置（VPC 内实例访问公网）

典型顺序：创建 NAT 网关 → 绑定 EIP → 创建 SNAT 规则

```
CreateNatGateway (RegionId, VpcId, VSwitchId, NatType="Enhanced")
  ↓ 返回 NatGatewayId, SnatTableIds
AllocateEipAddress (RegionId, Bandwidth)
  ↓ 返回 AllocationId, EipAddress
AssociateEipAddress (AllocationId, InstanceId=NatGatewayId, InstanceType="Nat")
CreateSnatEntry (RegionId, SnatTableId, SourceVSwitchId, SnatIp=EipAddress)
```

注意：
- NatType 推荐使用 "Enhanced"（增强型），不再推荐普通型
- CreateNatGateway 是异步接口，等待 Available 后再操作
- 一个交换机只能属于一个 SNAT 条目
- 多 EIP 可配置 SNAT IP 地址池，建议加入同一共享带宽避免单 EIP 带宽瓶颈

## 3. NAT 网关 + DNAT 配置（公网访问 VPC 内实例）

```
# 假设 NAT 网关和 EIP 已创建并绑定（见上一节）
CreateForwardEntry (RegionId, ForwardTableId, ExternalIp, ExternalPort, InternalIp, InternalPort, IpProtocol)
```

注意：
- IpProtocol 取值：TCP, UDP, Any
- ExternalPort 和 InternalPort 可以用 "any" 表示所有端口
- DNAT 条目的公网 IP 不能同时用于 SNAT

## 4. 站点到站点 VPN 连接

典型顺序：创建 VPN 网关 → 创建用户网关 → 创建 IPsec 连接

```
CreateVpnGateway (RegionId, VpcId, Bandwidth, EnableIpsec=true)
  ↓ 返回 VpnGatewayId（异步，等待 Active）
CreateCustomerGateway (RegionId, IpAddress=对端公网IP)
  ↓ 返回 CustomerGatewayId
CreateVpnConnection (RegionId, VpnGatewayId, CustomerGatewayId, LocalSubnet, RemoteSubnet, IkeConfig, IpsecConfig)
  ↓ 返回 VpnConnectionId
CreateVpnRouteEntry (RegionId, VpnGatewayId, RouteDest, NextHop=VpnConnectionId, PublishVpc=true)
```

注意：
- VPN 网关创建是异步的，通常需要 1-5 分钟
- IkeConfig 和 IpsecConfig 是 JSON 字符串，包含加密算法/DH组/生命周期等
- LocalSubnet 和 RemoteSubnet 支持多网段（逗号分隔）
- PublishVpc=true 会自动将 VPN 路由发布到 VPC 路由表

## 5. SSL-VPN（点到站点）

```
CreateVpnGateway (RegionId, VpcId, Bandwidth, EnableSsl=true, SslConnections=5)
  ↓ 返回 VpnGatewayId
CreateSslVpnServer (RegionId, VpnGatewayId, ClientIpPool, LocalSubnet)
  ↓ 返回 SslVpnServerId
CreateSslVpnClientCert (RegionId, SslVpnServerId)
  ↓ 返回 SslVpnClientCertId（下载证书供客户端使用）
```

## 6. EIP 分配与绑定

```
AllocateEipAddress (RegionId, Bandwidth, InternetChargeType="PayByTraffic")
  ↓ 返回 AllocationId, EipAddress
AssociateEipAddress (AllocationId, InstanceId, InstanceType)
```

InstanceType 可选值：
- Nat — NAT 网关
- EcsInstance — ECS 实例
- SlbInstance — SLB 实例
- NetworkInterface — 弹性网卡
- HaVip — 高可用虚拟 IP

释放流程（需先解绑）：
```
UnassociateEipAddress (AllocationId, InstanceId, InstanceType)
ReleaseEipAddress (AllocationId)
```

## 7. 物理专线 + VBR 接入

```
CreatePhysicalConnection (RegionId, AccessPointId, LineOperator, bandwidth)
  ↓ 返回 PhysicalConnectionId（审批后启用）
EnablePhysicalConnection (RegionId, PhysicalConnectionId)
CreateVirtualBorderRouter (RegionId, PhysicalConnectionId, VlanId, LocalGatewayIp, PeerGatewayIp, PeeringSubnetMask)
  ↓ 返回 VbrId
```

VBR 创建后通常需要配置 BGP：
```
CreateBgpGroup (RegionId, RouterId=VbrId, PeerAsn)
  ↓ 返回 BgpGroupId
CreateBgpPeer (RegionId, BgpGroupId, PeerIpAddress)
AddBgpNetwork (RegionId, RouterId=VbrId, DstCidrBlock)
```

## 通用注意事项

- **异步接口**: CreateVpc, CreateNatGateway, CreateVpnGateway, CreateSnatEntry 等都是异步接口，返回 ID 后需要轮询对应的 Describe 接口等待状态就绪
- **幂等性**: 大部分创建接口支持 ClientToken 参数实现幂等
- **DryRun**: 大部分接口支持 DryRun=true 做预检，不会真正执行
- **地域**: 几乎所有接口都需要 RegionId，VPC 相关资源必须在同一地域
- **endpoint 格式**: `vpc.{regionId}.aliyuncs.com`，用 `query.py endpoint` 查询具体值
