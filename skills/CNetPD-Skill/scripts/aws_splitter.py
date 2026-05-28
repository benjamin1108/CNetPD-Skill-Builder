"""Split AWS Smithy JSON AST models into progressive CNetPD data layers."""

from __future__ import annotations

import copy
import html
import json
import re
import time
from pathlib import Path

try:
    from .constants import AWS_PROVIDER, AWS_PRODUCTS
except ImportError:  # Runtime copy lives directly under scripts/.
    from cnetpd_constants import AWS_PROVIDER, AWS_PRODUCTS  # type: ignore

VERSION = "2.1.0"

EC2_EXPLICIT_OPS = {"CreateTags", "DeleteTags", "DescribeTags", "DescribeRegions", "DescribeAvailabilityZones"}
EC2_NETWORK_RE = re.compile(
    r"Vpc|Subnet|Route|Gateway|Vpn|Ipam|Address|Ipv6|Cidr|SecurityGroup|NetworkAcl|"
    r"NetworkInterface|NetworkInsights|Peering|VpcEndpoint|EndpointService|NatGateway|"
    r"FlowLog|TrafficMirror|TransitGateway|DhcpOptions|AvailabilityZone|LocalZone|"
    r"Wavelength|PrefixList|VerifiedAccess|CustomerGateway|InternetGateway|Byoip|Coip|"
    r"MacSec|CarrierGateway|RouteServer|PrivateIp|PublicIpv4|ElasticIp|Acl"
)

EC2_GROUPS = [
    ("vpc-core", "VPC / Subnet / AZ", ["Vpc", "Subnet", "Dhcp", "AvailabilityZone", "LocalZone", "Wavelength", "Regions"]),
    ("routing-gateways", "路由与网关", ["Route", "InternetGateway", "NatGateway", "EgressOnly", "CarrierGateway", "LocalGateway", "RouteServer"]),
    ("security-access", "安全与访问控制", ["SecurityGroup", "NetworkAcl", "VerifiedAccess", "Acl"]),
    ("private-connect", "私网连接", ["VpcEndpoint", "EndpointService", "Peering", "PrefixList"]),
    ("hybrid-connectivity", "混合云与跨 VPC", ["TransitGateway", "Vpn", "CustomerGateway"]),
    ("ip-addressing", "IP 地址与 IPAM", ["Ipam", "Address", "Ipv6", "Cidr", "Byoip", "Coip", "PublicIpv4", "PrivateIp"]),
    ("network-interfaces", "弹性网卡", ["NetworkInterface", "TrunkInterface"]),
    ("observability", "网络诊断与可观测", ["FlowLog", "TrafficMirror", "NetworkInsights", "NetworkPerformance"]),
    ("tags", "标签", ["Tags", "Tag"]),
]

VERBS = [
    "Batch", "Create", "Delete", "Describe", "List", "Get", "Put", "Update", "Modify", "Add",
    "Remove", "Associate", "Disassociate", "Attach", "Detach", "Enable", "Disable", "Start",
    "Stop", "Accept", "Reject", "Register", "Deregister", "Import", "Export", "Provision",
    "Deprovision", "Allocate", "Release", "Assign", "Unassign", "Authorize", "Revoke", "Set",
    "Reset", "Tag", "Untag", "Untag", "Test", "Check",
]


def clean_doc(value: str | None, *, limit: int | None = None) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<(script|style).*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def shape_local(shape_id: str) -> str:
    return shape_id.split("#", 1)[-1]


def target_of(ref: dict | None) -> str:
    return ref.get("target", "") if isinstance(ref, dict) else ""


def service_shape(data: dict) -> tuple[str, dict]:
    for shape_id, shape in data.get("shapes", {}).items():
        if isinstance(shape, dict) and shape.get("type") == "service":
            return shape_id, shape
    raise RuntimeError("AWS model missing service shape")


def service_info(data: dict, source_service: str) -> dict:
    shape_id, shape = service_shape(data)
    traits = shape.get("traits", {})
    aws_service = traits.get("aws.api#service", {})
    return {
        "shapeId": shape_id,
        "sdkId": aws_service.get("sdkId") or shape_local(shape_id),
        "arnNamespace": aws_service.get("arnNamespace", ""),
        "endpointPrefix": aws_service.get("endpointPrefix", source_service),
        "version": shape.get("version", ""),
        "title": traits.get("smithy.api#title", ""),
        "documentation": clean_doc(traits.get("smithy.api#documentation"), limit=700),
        "protocols": sorted(key for key in traits if key.startswith("aws.protocols#")),
    }


def operation_ids(data: dict) -> list[str]:
    _shape_id, shape = service_shape(data)
    shapes = data.get("shapes", {})
    ordered = [target_of(item) for item in shape.get("operations", [])]
    ordered = [item for item in ordered if item in shapes and shapes[item].get("type") == "operation"]
    rest = sorted(
        shape_id
        for shape_id, item in shapes.items()
        if isinstance(item, dict) and item.get("type") == "operation" and shape_id not in ordered
    )
    return [*ordered, *rest]


def selected_operation_ids(data: dict, product: dict) -> list[str]:
    ids = operation_ids(data)
    if product.get("operationFilter") != "ec2-networking":
        return ids
    shapes = data.get("shapes", {})
    selected = []
    for shape_id in ids:
        name = shape_local(shape_id)
        op = shapes[shape_id]
        text = " ".join([
            name,
            shape_local(target_of(op.get("input"))),
            shape_local(target_of(op.get("output"))),
        ])
        if name in EC2_EXPLICIT_OPS or EC2_NETWORK_RE.search(text):
            selected.append(shape_id)
    return selected


def shape_type(shapes: dict, shape_id: str) -> str:
    shape = shapes.get(shape_id, {})
    return shape.get("type", "") if isinstance(shape, dict) else ""


def member_summary(name: str, member: dict, shapes: dict) -> dict:
    target = target_of(member)
    traits = member.get("traits", {}) if isinstance(member, dict) else {}
    target_shape = shapes.get(target, {}) if target else {}
    doc = traits.get("smithy.api#documentation") or target_shape.get("traits", {}).get("smithy.api#documentation", "")
    item = {
        "name": name,
        "target": shape_local(target),
        "schema": {
            "type": shape_type(shapes, target),
            "target": shape_local(target),
            "description": clean_doc(doc, limit=180),
        },
    }
    if "smithy.api#required" in traits:
        item["required"] = True
    return item


def structure_members(shape_id: str, shapes: dict) -> list[dict]:
    shape = shapes.get(shape_id, {})
    members = shape.get("members", {}) if isinstance(shape, dict) else {}
    return [member_summary(name, member, shapes) for name, member in members.items()]


def required_members(shape_id: str, shapes: dict) -> list[str]:
    return [
        item["name"]
        for item in structure_members(shape_id, shapes)
        if item.get("required")
    ]


def response_fields(shape_id: str, shapes: dict) -> list[str]:
    return [item["name"] for item in structure_members(shape_id, shapes)[:20]]


def refs_in(value) -> list[str]:
    refs = []
    if isinstance(value, dict):
        target = value.get("target")
        if isinstance(target, str):
            refs.append(target)
        for item in value.values():
            refs.extend(refs_in(item))
    elif isinstance(value, list):
        for item in value:
            refs.extend(refs_in(item))
    return refs


def shape_closure(start_ids: list[str], shapes: dict) -> dict:
    queue = list(start_ids)
    seen: set[str] = set()
    result = {}
    while queue:
        shape_id = queue.pop(0)
        if shape_id in seen or shape_id not in shapes:
            continue
        seen.add(shape_id)
        shape = copy.deepcopy(shapes[shape_id])
        result[shape_local(shape_id)] = {"shapeId": shape_id, "shape": shape}
        for ref in refs_in(shape):
            if ref not in seen:
                queue.append(ref)
    return result


def operation_resource(name: str) -> str:
    base = name
    for verb in sorted(VERBS, key=len, reverse=True):
        if base.startswith(verb) and len(base) > len(verb):
            base = base[len(verb):]
            break
    words = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|\d+", base)
    return "-".join(word.lower() for word in words[:3]) or "operations"


def group_for_operation(name: str, product: dict) -> tuple[str, str]:
    if product.get("operationFilter") == "ec2-networking":
        for slug, title, terms in EC2_GROUPS:
            if any(term in name for term in terms):
                return slug, title
    slug = operation_resource(name)
    title = " ".join(part.capitalize() for part in slug.split("-"))
    return slug, title


def api_summary(shape_id: str, op: dict, shapes: dict, group: str) -> dict:
    name = shape_local(shape_id)
    input_id = target_of(op.get("input"))
    output_id = target_of(op.get("output"))
    params = structure_members(input_id, shapes)
    item = {
        "name": name,
        "summary": clean_doc(op.get("traits", {}).get("smithy.api#documentation"), limit=220),
        "operationType": op.get("type", "operation"),
        "required": required_members(input_id, shapes),
        "optional": [
            {"name": p["name"], "type": p.get("schema", {}).get("type", ""), "note": p.get("schema", {}).get("description", "")}
            for p in params
            if not p.get("required")
        ][:20],
        "returns": response_fields(output_id, shapes),
        "group": group,
    }
    errors = op.get("errors", [])
    if errors:
        item["errorCount"] = len(errors)
    return {key: value for key, value in item.items() if value not in ("", None, [], {})}


def api_detail(provider: str, product: dict, source_service: str, shape_id: str, op: dict, shapes: dict, group: str) -> dict:
    input_id = target_of(op.get("input"))
    output_id = target_of(op.get("output"))
    error_ids = [target_of(item) for item in op.get("errors", []) if target_of(item)]
    start_ids = [shape_id, input_id, output_id, *error_ids]
    detail = {
        "_layer": "L2",
        "_version": VERSION,
        "provider": provider,
        "product": product["product"],
        "sourceService": source_service,
        "api": shape_local(shape_id),
        "shapeId": shape_id,
        "group": group,
        "title": shape_local(shape_id),
        "description": clean_doc(op.get("traits", {}).get("smithy.api#documentation")),
        "operation": copy.deepcopy(op),
        "input": {"target": shape_local(input_id), "shapeId": input_id, "members": structure_members(input_id, shapes)} if input_id else {},
        "output": {"target": shape_local(output_id), "shapeId": output_id, "members": structure_members(output_id, shapes)} if output_id else {},
        "errors": [{"target": shape_local(item), "shapeId": item, "shape": copy.deepcopy(shapes.get(item, {}))} for item in error_ids],
        "parameters": structure_members(input_id, shapes),
        "shapeClosure": shape_closure([item for item in start_ids if item], shapes),
    }
    traits = op.get("traits", {})
    if traits.get("smithy.api#examples"):
        detail["examples"] = copy.deepcopy(traits["smithy.api#examples"])
    return {key: value for key, value in detail.items() if value not in ("", None, [], {})}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def find_model(source_dir: Path, source_service: str) -> Path | None:
    roots = [source_dir / source_service / "service", source_dir / "models" / source_service / "service"]
    for root in roots:
        candidates = sorted(root.glob("*/*.json"))
        if candidates:
            return candidates[-1]
    candidates = sorted(
        path for path in source_dir.rglob("*.json")
        if source_service in path.parts and path.parent.parent.name == "service"
    )
    return candidates[-1] if candidates else None


def split_product(source: Path, output_dir: Path, product: dict) -> dict:
    data = json.loads(source.read_text(encoding="utf-8"))
    shapes = data.get("shapes", {})
    source_service = product.get("sourceService", product["product"])
    info = service_info(data, source_service)
    selected_ids = selected_operation_ids(data, product)
    product_dir = output_dir / product["product"]
    groups_dir = product_dir / "groups"
    apis_dir = product_dir / "apis"
    groups: dict[str, dict] = {}

    for shape_id in selected_ids:
        name = shape_local(shape_id)
        slug, title = group_for_operation(name, product)
        groups.setdefault(slug, {"title": title, "apis": []})
        groups[slug]["apis"].append(api_summary(shape_id, shapes[shape_id], shapes, slug))
        write_json(apis_dir / f"{name}.json", api_detail(AWS_PROVIDER, product, source_service, shape_id, shapes[shape_id], shapes, slug))

    group_entries = []
    for slug, group in sorted(groups.items()):
        apis = sorted(group["apis"], key=lambda item: item["name"])
        write_json(groups_dir / f"{slug}.json", {
            "_layer": "L1",
            "_version": VERSION,
            "provider": AWS_PROVIDER,
            "product": product["product"],
            "sourceService": source_service,
            "group": slug,
            "title": group["title"],
            "apiCount": len(apis),
            "apis": apis,
        })
        group_entries.append({"slug": slug, "title": group["title"], "count": len(apis)})

    write_json(product_dir / "source-model.json", data)
    write_json(product_dir / "index.json", {
        "_layer": "L0",
        "_version": VERSION,
        "provider": AWS_PROVIDER,
        "product": product["product"],
        "sourceService": source_service,
        "sourceModel": "source-model.json",
        "sdkId": info["sdkId"],
        "version": info["version"],
        "endpointPrefix": info["endpointPrefix"],
        "arnNamespace": info["arnNamespace"],
        "protocols": info["protocols"],
        "description": info["documentation"],
        "totalApis": len(selected_ids),
        "sourceOperationCount": len(operation_ids(data)),
        "groups": group_entries,
    })
    return {
        "product": product["product"],
        "sourceService": source_service,
        "api_count": len(selected_ids),
        "source_api_count": len(operation_ids(data)),
        "group_count": len(group_entries),
        "files_written": len(selected_ids) + len(group_entries) + 2,
        "errors": [],
    }


def validate_output(product_dir: Path, expected_names: set[str]) -> list[str]:
    issues = []
    found = set()
    for group_file in (product_dir / "groups").glob("*.json"):
        group = json.loads(group_file.read_text(encoding="utf-8"))
        found.update(api.get("name") for api in group.get("apis", []))
    missing = sorted(expected_names - found)
    api_files_missing = sorted(name for name in expected_names if not (product_dir / "apis" / f"{name}.json").exists())
    if missing:
        issues.append(f"index 中缺少 {len(missing)} 个 API: {missing[:10]}")
    if api_files_missing:
        issues.append(f"缺少 {len(api_files_missing)} 个 L2 文件: {api_files_missing[:10]}")
    if not (product_dir / "source-model.json").exists():
        issues.append("缺少 source-model.json")
    return issues


def split_batch(source_dir: Path, output_dir: Path, *, products: list[dict] | None = None, validate: bool = True) -> dict:
    products = products or AWS_PRODUCTS
    output_dir.mkdir(parents=True, exist_ok=True)
    totals = {"api_count": 0, "source_api_count": 0, "group_count": 0, "files_written": 0, "errors": [], "products": []}
    catalog = []
    for product in products:
        source_service = product.get("sourceService", product["product"])
        source = find_model(source_dir, source_service)
        if source is None:
            totals["errors"].append(f"[{product['product']}] missing AWS model for {source_service}")
            continue
        stats = split_product(source, output_dir, product)
        totals["api_count"] += stats["api_count"]
        totals["source_api_count"] += stats["source_api_count"]
        totals["group_count"] += stats["group_count"]
        totals["files_written"] += stats["files_written"]
        totals["products"].append(product["product"])
        if validate:
            data = json.loads(source.read_text(encoding="utf-8"))
            expected = {shape_local(item) for item in selected_operation_ids(data, product)}
            totals["errors"].extend(f"[{product['product']}] 验证: {issue}" for issue in validate_output(output_dir / product["product"], expected))
        catalog.append({
            "provider": AWS_PROVIDER,
            "product": product["product"],
            "sourceService": source_service,
            "apiCount": stats["api_count"],
            "sourceApiCount": stats["source_api_count"],
            "groupCount": stats["group_count"],
            "index": f"{product['product']}/index.json",
        })

    write_json(output_dir / "_catalog.json", {
        "_version": VERSION,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "productCount": len(catalog),
        "products": catalog,
    })
    write_json(output_dir / "_report.json", totals)
    return totals
