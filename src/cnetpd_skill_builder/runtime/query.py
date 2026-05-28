#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Runtime query tool for CNetPD-Skill."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from cnetpd_constants import (  # type: ignore
        GITHUB_SKILL_SOURCE_URL,
        INSTALL_COMMAND,
        LATEST_VERSION_URL,
        DEFAULT_SYNC_TTL_DAYS,
        DATA_SCHEMA_VERSION,
        SKILL_NAME,
        SKILL_VERSION,
        SOURCE_REPO,
        SOURCE_URL,
        UPDATE_COMMAND,
        UPDATE_COMMAND_GLOBAL,
    )
except ImportError:
    GITHUB_SKILL_SOURCE_URL = "https://github.com/benjamin1108/CNetPD-Skill-Builder/tree/main/skills/CNetPD-Skill"
    INSTALL_COMMAND = "npx skills add benjamin1108/CNetPD-Skill-Builder --skill CNetPD-Skill"
    LATEST_VERSION_URL = "https://api.github.com/repos/benjamin1108/CNetPD-Skill-Builder/contents/version.json?ref=main"
    DEFAULT_SYNC_TTL_DAYS = 30
    DATA_SCHEMA_VERSION = 2
    SKILL_NAME = "CNetPD-Skill"
    SKILL_VERSION = "1.1.0"
    SOURCE_REPO = "benjamin1108/CNetPD-Skill-Builder"
    SOURCE_URL = "https://github.com/benjamin1108/CNetPD-Skill-Builder"
    UPDATE_COMMAND = "npx skills update CNetPD-Skill"
    UPDATE_COMMAND_GLOBAL = UPDATE_COMMAND

SKILL_ROOT = SCRIPT_DIR.parent
PACKAGED_DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
CACHE_DATA_ROOT = Path(os.environ.get("CNETPD_CACHE_DIR", Path.home() / ".cache" / "cnetpd-skill" / "data")).expanduser()
SYNC_SCRIPT = SCRIPT_DIR / "sync_data.py"
DEFAULT_PROVIDER = "aliyun"
VERSION_CHECK_OFF = {"0", "false", "no", "off"}
DEFAULT_UPDATE_TIMEOUT_SECONDS = 180
DIRECT_UPDATE_TIMEOUT_SECONDS = 90


def read_json(path: Path) -> dict: return json.loads(path.read_text(encoding="utf-8"))


def valid_data_root(root: Path) -> bool:
    if not ((root / "_cnetpd-index.json").exists() and (root / "_manifest.json").exists()):
        return False
    try:
        return int(manifest(root).get("schema_version", 0)) >= DATA_SCHEMA_VERSION
    except (TypeError, ValueError):
        return False


def manifest(root: Path) -> dict:
    try:
        return read_json(root / "_manifest.json")
    except (OSError, json.JSONDecodeError):
        return {}


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def sync_ttl() -> timedelta:
    try:
        return timedelta(days=max(1, int(os.environ.get("CNETPD_SYNC_TTL_DAYS", str(DEFAULT_SYNC_TTL_DAYS)))))
    except ValueError:
        return timedelta(days=DEFAULT_SYNC_TTL_DAYS)


def stale(root: Path) -> bool:
    generated_at = parse_dt(manifest(root).get("generated_at"))
    if generated_at is None:
        return True
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - generated_at > sync_ttl()


def auto_sync_enabled() -> bool: return os.environ.get("CNETPD_AUTO_SYNC", "1").lower() not in {"0", "false", "no", "off"}


def attempt_file() -> Path: return CACHE_DATA_ROOT.parent / ".last_sync_attempt"


def recent_attempt() -> bool:
    try:
        last = parse_dt(attempt_file().read_text(encoding="utf-8").strip())
    except OSError:
        return False
    return bool(last and datetime.now(timezone.utc) - last < timedelta(hours=6))


def mark_attempt() -> None:
    path = attempt_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")


def run_sync(*, quiet: bool, force: bool = False) -> bool:
    if not SYNC_SCRIPT.exists():
        return False
    cmd = [sys.executable, str(SYNC_SCRIPT), "--target", str(CACHE_DATA_ROOT)]
    if force:
        cmd.append("--force")
    if quiet:
        cmd.append("--quiet")
    result = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE if quiet else None,
        stderr=subprocess.PIPE if quiet else None,
    )
    return result.returncode == 0


def maybe_auto_sync() -> None:
    if os.environ.get("CNETPD_DATA") or not auto_sync_enabled():
        return
    if valid_data_root(CACHE_DATA_ROOT) and not stale(CACHE_DATA_ROOT):
        return
    if recent_attempt():
        return
    try:
        mark_attempt()
        run_sync(quiet=True, force=not valid_data_root(CACHE_DATA_ROOT))
    except OSError:
        return


def select_data_root() -> tuple[str, Path]:
    override = os.environ.get("CNETPD_DATA")
    if override:
        return "override", Path(override).expanduser()
    maybe_auto_sync()
    if valid_data_root(CACHE_DATA_ROOT):
        return "cache", CACHE_DATA_ROOT
    if valid_data_root(PACKAGED_DATA_ROOT):
        return "packaged", PACKAGED_DATA_ROOT
    return "none", PACKAGED_DATA_ROOT


DATA_SOURCE = "none"
DATA_ROOT = PACKAGED_DATA_ROOT


def init_data_root() -> None:
    global DATA_SOURCE, DATA_ROOT
    DATA_SOURCE, DATA_ROOT = select_data_root()


def index() -> dict:
    return read_json(DATA_ROOT / "_cnetpd-index.json")


def product_dir(product: str, provider: str) -> Path | None:
    root = DATA_ROOT / "providers" / provider
    if not root.exists():
        return None
    needle = product.lower()
    for path in root.iterdir():
        if path.is_dir() and path.name.lower() == needle:
            return path
    return None


def cmd_domain() -> None:
    idx = index()
    print(f"Skill: {idx['skill']}  |  Domain: {idx['domain']}")
    print(f"Providers: {len(idx['providers'])}  |  Products: {idx['productCount']}  |  Topics: {idx['topicCount']}\n")
    print("【Providers】")
    for provider in idx["providers"]:
        print(f"  {provider['slug']:<10} {provider['display']}  {provider['productCount']} products")
    print("\n【Topics】")
    for topic in idx["topics"]:
        products = "、".join(f"{p['provider']}/{p['product']}" for p in topic["products"])
        print(f"  {topic['slug']:<18} {topic['title']}  {products}")


def cmd_providers() -> None:
    for provider in index()["providers"]:
        print(f"{provider['slug']:<10} {provider['display']}  {provider['productCount']} products")


def cmd_topics() -> None:
    for topic in index()["topics"]:
        print(f"{topic['slug']:<18} {topic['title']}")
        print(f"  {topic['description']}\n")


def cmd_topic(slug: str) -> None:
    idx = index()
    topic = next((item for item in idx["topics"] if item["slug"] == slug), None)
    if not topic:
        print("可用主题: " + ", ".join(item["slug"] for item in idx["topics"]))
        return
    print(f"【{topic['title']}】{topic['description']}\n")
    print("候选产品:")
    for item in topic["products"]:
        print(f"  {item['provider']}/{item['product']:<24} {item['role']}")
    print("\n选型决策:")
    for decision in topic["decisions"]:
        print(f"  - 当 {decision['when']} -> {decision['use']}")
    relevant = topic.get("relevantApis", {})
    if relevant:
        print("\n相关 API:")
        for key, apis in relevant.items():
            print(f"  {key}: " + ", ".join(api["api"] for api in apis[:8]))


def cmd_product(product: str, provider: str) -> None:
    root = product_dir(product, provider)
    if not root:
        print(f"未找到产品: {provider}/{product}")
        return
    data = read_json(root / "index.json")
    print(f"产品: {provider}/{data.get('product', product)}  |  {data.get('totalApis', '?')} APIs\n")
    if data.get("sourceService") and data.get("sourceService") != data.get("product"):
        print(f"源服务: {data.get('sourceService')}  |  源模型 API: {data.get('sourceOperationCount', '?')}\n")
    print(f"{'Slug':<24} {'能力分区':<20} {'API数':>5}")
    print("-" * 56)
    for group in data.get("groups", []):
        print(f"{group['slug']:<24} {group['title']:<20} {group['count']:>5}")


def cmd_group(slug: str, product: str, provider: str) -> None:
    root = product_dir(product, provider)
    if not root:
        print(f"未找到产品: {provider}/{product}")
        return
    group_file = root / "groups" / f"{slug}.json"
    if not group_file.exists():
        print(f"未找到分区: {slug}")
        return
    group = read_json(group_file)
    print(f"【{group['title']}】{provider}/{product}  {len(group['apis'])} APIs\n")
    for api in group["apis"]:
        print(f"  {api['name']} [{api.get('operationType', '')}]")
        print(f"    {api.get('summary', '')}")
        if api.get("required"):
            print(f"    必填: {', '.join(api['required'])}")


def collect_text(value: object) -> list[str]:
    if isinstance(value, dict):
        parts: list[str] = []
        for key, item in value.items():
            parts.append(str(key))
            parts.extend(collect_text(item))
        return parts
    if isinstance(value, list):
        parts = []
        for item in value:
            parts.extend(collect_text(item))
        return parts
    if isinstance(value, str):
        return [value]
    if value is None:
        return []
    return [str(value)]


def match_snippet(parts: list[str], keyword: str, *, limit: int = 150) -> str:
    kw = keyword.lower()
    for part in parts:
        compact = " ".join(part.split())
        pos = compact.lower().find(kw)
        if pos < 0:
            continue
        start = max(0, pos - 50)
        end = min(len(compact), pos + len(keyword) + 80)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(compact) else ""
        return (prefix + compact[start:end] + suffix)[:limit]
    return ""


def cmd_search(keyword: str, provider: str | None) -> None:
    kw = keyword.lower()
    providers = [provider] if provider else [item["slug"] for item in index()["providers"]]
    total = 0
    for provider_slug in providers:
        root = DATA_ROOT / "providers" / provider_slug
        if not root.exists():
            continue
        for product in sorted(path.name for path in root.iterdir() if path.is_dir()):
            hits = []
            for api_file in sorted((root / product / "apis").glob("*.json")):
                api = read_json(api_file)
                parts = collect_text(api)
                haystack = " ".join(parts).lower()
                if kw in haystack:
                    hits.append((api.get("group", ""), api, match_snippet(parts, keyword)))
            if hits:
                print(f"\n【{provider_slug}/{product}】{len(hits)} matches")
                for group, api, snippet in hits[:15]:
                    desc_lines = api.get("description", "").splitlines()
                    summary = api.get("summary") or (desc_lines[0] if desc_lines else "")
                    print(f"  {api['api']} ({group}) - {summary}")
                    if snippet:
                        print(f"    命中: {snippet}")
                total += len(hits)
    if total == 0:
        print(f"未找到: {keyword}")


def print_param(param: dict) -> None:
    schema = param.get("schema", {})
    name = param.get("name", "")
    typ = schema.get("type", "")
    loc = f" ({param.get('in')})" if param.get("in") else ""
    print(f"  {name}: {typ}{loc}")
    desc = schema.get("description")
    if desc:
        print(f"      {desc.splitlines()[0][:120]}")


def cmd_detail(api_name: str, product: str, provider: str, full: bool = False) -> None:
    root = product_dir(product, provider)
    if not root:
        print(f"未找到产品: {provider}/{product}")
        return
    api_file = root / "apis" / f"{api_name}.json"
    if not api_file.exists():
        candidates = [path.stem for path in (root / "apis").glob("*.json") if api_name.lower() in path.stem.lower()]
        print("候选: " + ", ".join(candidates[:10]) if candidates else f"未找到 API: {api_name}")
        return
    api = read_json(api_file)
    print(f"能力: {provider}/{product}/{api.get('api', api_name)}")
    print(f"分区: {api.get('group', '')}")
    print(f"标题: {api.get('title', '')}")
    if provider == "aws":
        print(f"Smithy: {api.get('shapeId', '')}  |  sourceService={api.get('sourceService', product)}")
    if api.get("deprecated"):
        print("状态: 已废弃")
    desc = api.get("description", "")
    if desc:
        lines = [line.strip() for line in desc.splitlines() if line.strip()]
        print("\n说明:")
        for line in lines[:20 if full else 6]:
            print(f"  {line}")
    params = api.get("parameters", [])
    if params:
        print("\n参数:")
        for param in params[:50 if full else 20]:
            print_param(param)
    fields = []
    for response in api.get("responses", {}).values():
        schema = response.get("schema", {}) if isinstance(response, dict) else {}
        fields.extend(name for name in schema.get("properties", {}) if name != "RequestId")
    if not fields and isinstance(api.get("output"), dict):
        fields.extend(item.get("name", "") for item in api["output"].get("members", []))
    if fields:
        print("\n返回字段: " + ", ".join(dict.fromkeys(fields)))
    if provider == "aws":
        errors = [item.get("target", "") for item in api.get("errors", [])]
        if errors:
            print("\n错误形状: " + ", ".join(errors))
        print("\n完整 Smithy 细节: L2 JSON 内含 operation/input/output/errors/shapeClosure；产品目录另有 source-model.json。")
        if full and api.get("shapeClosure"):
            print("Shape closure: " + ", ".join(sorted(api["shapeClosure"])[:80]))


def cmd_constraints(api_name: str, product: str, provider: str) -> None:
    root = product_dir(product, provider)
    api_file = root / "apis" / f"{api_name}.json" if root else None
    if not api_file or not api_file.exists():
        print(f"未找到 API: {provider}/{product}/{api_name}")
        return
    api = read_json(api_file)
    grouped = defaultdict(list)
    for status, errors in api.get("errorCodes", {}).items():
        for error in errors if isinstance(errors, list) else []:
            code = error.get("errorCode", "") if isinstance(error, dict) else str(error)
            grouped[status].append(code)
    for status, codes in grouped.items():
        print(f"{status}:")
        for code in codes:
            print(f"  {code}")


def cmd_data_info(*, no_remote: bool = False) -> None:
    meta = manifest(DATA_ROOT)
    local = local_version_info()
    print(f"数据源: {DATA_SOURCE}")
    print(f"路径: {DATA_ROOT}")
    print(f"有效: {'yes' if valid_data_root(DATA_ROOT) else 'no'}")
    print(f"生成时间: {meta.get('generated_at', 'unknown')}")
    print(f"schema: {meta.get('schema_version', 'unknown')}")
    print(f"providers: {', '.join(meta.get('providers', []))}")
    print(f"文件数: {meta.get('file_count', 'unknown')}")
    if DATA_SOURCE == "cache":
        print(f"缓存状态: {'过期' if stale(DATA_ROOT) else '新鲜'}")
    print(f"缓存目录: {CACHE_DATA_ROOT}")
    print("\n【Skill版本】")
    local_version, github_channel = print_version_header(local)
    print_remote_version_status(local, local_version, github_channel, no_remote=no_remote)


def local_version_info() -> dict:
    path = SKILL_ROOT / "version.json"
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError):
        data = {}
    data.setdefault("skill", SKILL_NAME)
    data.setdefault("version", SKILL_VERSION)
    data.setdefault("sourceRepo", SOURCE_REPO)
    data.setdefault("sourceUrl", SOURCE_URL)
    data.setdefault("githubSkillSourceUrl", GITHUB_SKILL_SOURCE_URL)
    data.setdefault("latestVersionUrl", LATEST_VERSION_URL)
    data.setdefault("installCommand", INSTALL_COMMAND)
    data.setdefault("updateCommand", UPDATE_COMMAND)
    data.setdefault("installChannels", {
        "npx": {
            "installCommand": INSTALL_COMMAND,
            "updateCommand": UPDATE_COMMAND,
        },
        "githubHomepage": {
            "homepage": SOURCE_URL,
            "skillSource": GITHUB_SKILL_SOURCE_URL,
        },
    })
    return data


def fetch_latest_version(timeout: int = 8) -> dict:
    latest_url = os.environ.get("CNETPD_LATEST_VERSION_URL", LATEST_VERSION_URL)
    request = urllib.request.Request(
        latest_url,
        headers={"User-Agent": f"{SKILL_NAME}/{SKILL_VERSION}", "Accept": "application/vnd.github.raw"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def version_tuple(value: str) -> tuple[int, int, int]:
    nums = [int(item) for item in re.findall(r"\d+", value)[:3]]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])


def remote_version_check_enabled() -> bool: return os.environ.get("CNETPD_VERSION_CHECK", "1").lower() not in VERSION_CHECK_OFF


def auto_update_enabled() -> bool: return os.environ.get("CNETPD_AUTO_UPDATE", "1").lower() not in VERSION_CHECK_OFF


def update_timeout_seconds() -> int:
    try:
        return max(10, int(os.environ.get("CNETPD_UPDATE_TIMEOUT_SECONDS", str(DEFAULT_UPDATE_TIMEOUT_SECONDS))))
    except ValueError:
        return DEFAULT_UPDATE_TIMEOUT_SECONDS


def command_skips_remote_check(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "no_remote", False)) or not remote_version_check_enabled()


def run_update_command(local: dict) -> subprocess.CompletedProcess[str]:
    command_text = os.environ.get("CNETPD_UPDATE_COMMAND", str(local.get("updateCommand", UPDATE_COMMAND)))
    command = shlex.split(command_text)
    if not command:
        raise RuntimeError("update command is empty")
    return subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=update_timeout_seconds(),
    )


def github_archive_url() -> str:
    return os.environ.get("CNETPD_SKILL_ARCHIVE_URL", f"https://api.github.com/repos/{SOURCE_REPO}/tarball/main")


def download_file(url: str, target: Path, *, timeout: int = DIRECT_UPDATE_TIMEOUT_SECONDS) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": f"{SKILL_NAME}/{SKILL_VERSION}"})
    with urllib.request.urlopen(request, timeout=timeout) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output)


def extract_skill_from_archive(archive_path: Path, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            parts = Path(member.name).parts
            if len(parts) < 3 or parts[1] != "skills" or parts[2] != SKILL_NAME:
                continue
            relative_parts = parts[3:]
            if not relative_parts:
                continue
            destination = target_dir.joinpath(*relative_parts)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            source = archive.extractfile(member)
            if source is None:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)
            try:
                destination.chmod(member.mode & 0o777)
            except OSError:
                pass
    required = [target_dir / "SKILL.md", target_dir / "version.json", target_dir / "scripts" / "query.py"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError("downloaded skill archive is incomplete: " + ", ".join(missing))
    return target_dir


def replace_current_skill(staged_skill: Path) -> None:
    for item in staged_skill.iterdir():
        destination = SKILL_ROOT / item.name
        if destination.exists():
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        if item.is_dir():
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)


def run_direct_current_dir_update() -> None:
    with tempfile.TemporaryDirectory(prefix="cnetpd-skill-update-") as tmp:
        tmp_dir = Path(tmp)
        archive_path = tmp_dir / "skill.tar.gz"
        staged_skill = tmp_dir / "skill"
        download_file(github_archive_url(), archive_path)
        extract_skill_from_archive(archive_path, staged_skill)
        replace_current_skill(staged_skill)


def print_command_output(result: subprocess.CompletedProcess[str]) -> None:
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if stdout:
        print(stdout, file=sys.stderr)
    if stderr:
        print(stderr, file=sys.stderr)


def maybe_self_update(args: argparse.Namespace) -> None:
    if command_skips_remote_check(args):
        return
    local = local_version_info()
    local_version = str(local.get("version", SKILL_VERSION))
    try:
        latest = fetch_latest_version()
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise SystemExit(
            "CNetPD-Skill 版本检查失败，已停止本次查询，避免使用过期 skill 得出结论。\n"
            f"原因: {exc}\n"
            "如果当前环境是沙箱、企业代理、DNS、TLS 或 HTTP 403/407 限制，请先允许联网后重试；"
            "确需离线继续时显式设置 CNETPD_VERSION_CHECK=0。"
        ) from exc
    latest_version = str(latest.get("version", "0.0.0"))
    if version_tuple(latest_version) <= version_tuple(local_version):
        return
    if not auto_update_enabled():
        raise SystemExit(
            f"CNetPD-Skill 有新版本: 本地 {local_version}, 最新 {latest_version}。\n"
            "自动更新已被 CNETPD_AUTO_UPDATE=0 关闭，因此本次查询停止。"
        )
    print(
        f"CNetPD-Skill 检测到新版本: {local_version} -> {latest_version}，正在自动更新...",
        file=sys.stderr,
    )
    result: subprocess.CompletedProcess[str] | None = None
    try:
        result = run_update_command(local)
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        print(f"CNetPD-Skill 标准更新命令失败，尝试直接更新当前脚本目录。原因: {exc}", file=sys.stderr)
        try:
            run_direct_current_dir_update()
        except (OSError, urllib.error.URLError, tarfile.TarError, RuntimeError) as fallback_exc:
            raise SystemExit(
                "CNetPD-Skill 自动更新失败，已停止本次查询。\n"
                f"标准更新失败原因: {exc}\n"
                f"直接更新失败原因: {fallback_exc}\n"
                f"可手动核查命令: {local.get('updateCommand', UPDATE_COMMAND)}"
            ) from fallback_exc
    else:
        if result.returncode != 0:
            print_command_output(result)
            print("CNetPD-Skill 标准更新命令返回失败，尝试直接更新当前脚本目录。", file=sys.stderr)
            try:
                run_direct_current_dir_update()
            except (OSError, urllib.error.URLError, tarfile.TarError, RuntimeError) as fallback_exc:
                raise SystemExit(
                    "CNetPD-Skill 自动更新命令返回失败，且直接更新当前目录也失败，已停止本次查询。\n"
                    f"命令: {local.get('updateCommand', UPDATE_COMMAND)}\n"
                    f"退出码: {result.returncode}\n"
                    f"直接更新失败原因: {fallback_exc}"
                ) from fallback_exc
    refreshed = local_version_info()
    refreshed_version = str(refreshed.get("version", SKILL_VERSION))
    if version_tuple(refreshed_version) < version_tuple(latest_version):
        if result is not None:
            print_command_output(result)
        print("CNetPD-Skill 标准更新未更新当前脚本目录，尝试直接更新当前脚本目录。", file=sys.stderr)
        try:
            run_direct_current_dir_update()
        except (OSError, urllib.error.URLError, tarfile.TarError, RuntimeError) as fallback_exc:
            raise SystemExit(
                "CNetPD-Skill 自动更新命令执行完成，但当前脚本目录仍不是最新版本，且直接更新失败，已停止本次查询。\n"
                f"当前脚本目录版本: {refreshed_version}; 最新版本: {latest_version}\n"
                f"直接更新失败原因: {fallback_exc}"
            ) from fallback_exc
        refreshed = local_version_info()
        refreshed_version = str(refreshed.get("version", SKILL_VERSION))
    if version_tuple(refreshed_version) < version_tuple(latest_version):
        raise SystemExit(
            "CNetPD-Skill 直接更新当前目录后仍不是最新版本，已停止本次查询。\n"
            f"当前脚本目录版本: {refreshed_version}; 最新版本: {latest_version}"
        )
    skill_md = SKILL_ROOT / "SKILL.md"
    print(
        f"CNetPD-Skill 自动更新完成: {local_version} -> {refreshed_version}。",
        file=sys.stderr,
    )
    print(f"CNETPD_SKILL_UPDATED: {skill_md}", file=sys.stderr)
    print("请 Agent 重新读取上述 SKILL.md 后，按新版说明继续原始请求。", file=sys.stderr)
    raise SystemExit(0)

def print_version_header(local: dict) -> tuple[str, dict]:
    local_version = str(local.get("version", SKILL_VERSION))
    channels = local.get("installChannels", {})
    github_channel = channels.get("githubHomepage", {}) if isinstance(channels, dict) else {}
    print(f"Skill: {local.get('skill', SKILL_NAME)}\n本地版本: {local_version}\n来源仓库: {local.get('sourceRepo', SOURCE_REPO)}\n安装命令: {local.get('installCommand', INSTALL_COMMAND)}\nGitHub主页: {github_channel.get('homepage', local.get('sourceUrl', SOURCE_URL))}\n手动安装源: {github_channel.get('skillSource', local.get('githubSkillSourceUrl', GITHUB_SKILL_SOURCE_URL))}")
    return local_version, github_channel

def print_remote_version_status(local: dict, local_version: str, github_channel: dict, *, no_remote: bool = False) -> None:
    if no_remote or not remote_version_check_enabled():
        print("远端检查: 已跳过")
        return
    try:
        latest = fetch_latest_version()
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"远端检查: 失败 ({exc})")
        print(f"如果当前环境是沙箱或企业代理限制，请先申请联网权限后重试版本检查。\n可重试: python3 {Path(__file__).resolve()} version")
        return
    latest_version = str(latest.get("version", "0.0.0"))
    print(f"最新版本: {latest_version}")
    latest_tuple = version_tuple(latest_version)
    local_tuple = version_tuple(local_version)
    if latest_tuple > local_tuple:
        print(f"状态: 有新版本\n查询脚本会在执行命令前自动更新；也可以手动执行:\n  {local.get('updateCommand', UPDATE_COMMAND)}")
        print("如果当前环境不支持 npx skills add:")
        print(f"  打开 {github_channel.get('homepage', local.get('sourceUrl', SOURCE_URL))}")
        print(f"  按对应客户端的方式安装或覆盖 {github_channel.get('skillSource', local.get('githubSkillSourceUrl', GITHUB_SKILL_SOURCE_URL))}")
    elif latest_tuple < local_tuple:
        print("状态: 本地版本高于远端（可能是未发布开发版）")
    else:
        print("状态: 已是最新")


def cmd_version(*, no_remote: bool = False) -> None:
    local = local_version_info()
    local_version, github_channel = print_version_header(local)
    print_remote_version_status(local, local_version, github_channel, no_remote=no_remote)


def main() -> None:
    parser = argparse.ArgumentParser(description="CNetPD-Skill query tool")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("domain")
    sub.add_parser("providers")
    sub.add_parser("topics")
    topic = sub.add_parser("topic"); topic.add_argument("slug")
    product = sub.add_parser("product"); product.add_argument("product"); product.add_argument("--provider", default=DEFAULT_PROVIDER)
    group = sub.add_parser("group"); group.add_argument("slug"); group.add_argument("--product", required=True); group.add_argument("--provider", default=DEFAULT_PROVIDER)
    search = sub.add_parser("search"); search.add_argument("keyword"); search.add_argument("--provider")
    detail = sub.add_parser("detail"); detail.add_argument("api_name"); detail.add_argument("--product", required=True); detail.add_argument("--provider", default=DEFAULT_PROVIDER); detail.add_argument("--full", action="store_true")
    constraints = sub.add_parser("constraints"); constraints.add_argument("api_name"); constraints.add_argument("--product", required=True); constraints.add_argument("--provider", default=DEFAULT_PROVIDER)
    data_info = sub.add_parser("data-info"); data_info.add_argument("--no-remote", action="store_true")
    version = sub.add_parser("version"); version.add_argument("--no-remote", action="store_true")
    check_update = sub.add_parser("check-update"); check_update.add_argument("--no-remote", action="store_true")
    sync = sub.add_parser("sync"); sync.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return
    maybe_self_update(args)
    init_data_root()
    data_free_commands = {"data-info", "sync", "version", "check-update"}
    if args.command not in data_free_commands and not valid_data_root(DATA_ROOT):
        raise SystemExit(f"数据目录无效: {DATA_ROOT}")
    dispatch = {
        "domain": lambda: cmd_domain(),
        "providers": lambda: cmd_providers(),
        "topics": lambda: cmd_topics(),
        "topic": lambda: cmd_topic(args.slug),
        "product": lambda: cmd_product(args.product, args.provider),
        "group": lambda: cmd_group(args.slug, args.product, args.provider),
        "search": lambda: cmd_search(args.keyword, args.provider),
        "detail": lambda: cmd_detail(args.api_name, args.product, args.provider, args.full),
        "constraints": lambda: cmd_constraints(args.api_name, args.product, args.provider),
        "data-info": lambda: cmd_data_info(no_remote=args.no_remote),
        "version": lambda: cmd_version(no_remote=args.no_remote),
        "check-update": lambda: cmd_version(no_remote=args.no_remote),
        "sync": lambda: sys.exit(0 if run_sync(quiet=False, force=args.force) else 1),
    }
    dispatch[args.command]()


if __name__ == "__main__":
    main()
