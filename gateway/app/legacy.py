#!/usr/bin/env python3
"""Persistent same-origin API for the home-dev dashboard."""
import hashlib
import filecmp
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import quote, urlparse

import yaml
import egress
import routing_groups as routing
import state

DATA = Path(os.environ.get("DATA_DIR", "/data")) / "dashboard"
CARDS = DATA / "cards.json"
MIHOMO_DIR = Path(os.environ.get("DATA_DIR", "/data")) / "mihomo"
MIHOMO_CONFIG = MIHOMO_DIR / "config.yaml"
MIHOMO = str(Path(os.environ.get("DATA_DIR", "/data")) / "components/current/mihomo/mihomo")
MIHOMO_API = "http://127.0.0.1:9090"
GATEWAY_KEYS = ("port", "socks-port", "redir-port", "mixed-port", "external-controller", "external-ui",
                "allow-lan", "bind-address", "tproxy-port", "dns", "tun", "routing-mark", "secret", "ipv6")
NETWORK_OWNED = {"dns": ("enable", "listen"),
                 "tun": ("enable", "device", "auto-route", "auto-detect-interface", "strict-route", "dns-hijack")}


def preserve_gateway_settings(candidate, current, edit_network=False):
    for key in GATEWAY_KEYS:
        if edit_network and key in NETWORK_OWNED and key in candidate:
            value = candidate[key]
            if not isinstance(value, dict):
                raise ValueError(f"{key} 必须是配置对象")
            active = current.get(key) or {}
            for field in NETWORK_OWNED[key]:
                if field in active:
                    value[field] = active[field]
                else:
                    value.pop(field, None)
            if not value and key not in current:
                candidate.pop(key)
        elif key in current:
            candidate[key] = current[key]
        else:
            candidate.pop(key, None)

def validate_providers(parsed):
    """Provider caches must stay inside this deployment's Mihomo data directory."""
    for kind in ("proxy-providers", "rule-providers"):
        providers = parsed.get(kind) or {}
        if not isinstance(providers, dict):
            raise ValueError("订阅配置必须为对象")
        for provider in providers.values():
            if not isinstance(provider, dict):
                raise ValueError("订阅配置无效")
            path = provider.get("path")
            if path:
                if not isinstance(path, str) or Path(path).is_absolute() or ".." in Path(path).parts:
                    raise ValueError("订阅缓存必须使用数据目录内的相对路径")
                resolved = (MIHOMO_DIR / path).resolve()
                if not resolved.is_relative_to(MIHOMO_DIR.resolve()) or resolved in (MIHOMO_CONFIG.resolve(), (MIHOMO_DIR / egress.RUNTIME_NAME).resolve()):
                    raise ValueError("订阅缓存必须位于 Mihomo 数据目录内且不能覆盖主配置")
        if kind in parsed:
            parsed[kind] = providers

def revision(content):
    return hashlib.sha256(content).hexdigest()

def read_cards():
    return state.read(CARDS, [])


def write_cards(cards):
    state.save(CARDS, cards)


def auth_headers():
    secret = (yaml.safe_load(MIHOMO_CONFIG.read_text()) or {}).get("secret", "")
    return {"Authorization": f"Bearer {secret}"} if secret else {}

def controller_request(path, method="GET", body=None, timeout=5):
    if method == "PUT" and path.split("?")[0] == "/configs" and body == {"path": str(MIHOMO_CONFIG)}:
        body = {"path": str(egress.runtime(MIHOMO_CONFIG))}
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(MIHOMO_API + path, data=data, method=method, headers=auth_headers())
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        return

    def validate_card(self, data):
        name, tag, url, note = (str(data.get(k, "")).strip() for k in ("name", "tag", "url", "note"))
        parsed = urlparse(url)
        if not name or not tag or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("请填写名称、分类和有效的 HTTP(S) 地址")
        if len(name) > 80 or len(tag) > 40 or len(url) > 500 or len(note) > 240:
            raise ValueError("输入内容过长")
        new_tab = data.get("open_in_new_tab", False)
        if not isinstance(new_tab, bool):
            raise ValueError("新页面打开设置必须是布尔值")
        return {"name": name, "tag": tag, "url": url, "note": note, "open_in_new_tab": new_tab}

    def apply_config(self):
        try:
            result = commit_proxy_config(self.body(4 * 1024 * 1024))
        except ConfigConflict as exc:
            self.reply(409, {"error": str(exc)})
        except Exception as exc:
            self.reply(400, {"error": str(exc) or "导入失败"})
        else:
            self.reply(200, result)


class ConfigConflict(ValueError):
    pass


def commit_proxy_config(data):
    with state.LOCK:
        result = apply_proxy_config(data)
        state.save(state.DASH / 'proxy-state.json', {'configured': True})
        return result


def apply_proxy_config(data):
    temp_path = None
    validation_dir = None
    try:
        content = str(data.get("content", ""))
        filename = str(data.get("filename", "config.yaml"))
        if not content or len(content.encode()) > 2 * 1024 * 1024:
            raise ValueError("配置文件为空或超过 2 MB")
        if (not 1 <= len(filename) <= 120 or Path(filename).name != filename or "\\" in filename
                or any(ord(c) < 32 for c in filename) or not filename.lower().endswith((".yaml", ".yml"))):
            raise ValueError("只支持 .yaml 或 .yml 配置文件")
        old = MIHOMO_CONFIG.read_bytes()
        if data.get("revision") != revision(old):
            raise ConfigConflict("The configuration has changed. Reopen the editor before saving.")
        parsed = yaml.safe_load(content)
        if not isinstance(parsed, dict) or not any(k in parsed for k in ("proxies", "proxy-providers", "proxy-groups")):
            raise ValueError("不是有效的 Mihomo 配置文件")
        validate_providers(parsed)
        current = yaml.safe_load(old)
        # Uploads change nodes and rules while keeping this gateway reachable.
        preserve_gateway_settings(parsed, current, edit_network=data.get("edit_network") is True)
        # Subscriptions may define other host overrides, but the gateway's
        # configured local name must always keep resolving to this installation.
        from state import settings, lan_ip
        hosts = parsed.setdefault("hosts", {})
        if not isinstance(hosts, dict):
            raise ValueError("hosts 必须为域名映射对象")
        hosts[settings()["domain"]] = lan_ip()
        # Ordinary saves keep healthy existing subscriptions offline. Explicit
        # subscription refreshes still fetch every provider, even for the same YAML.
        refresh_providers = set()
        previous_providers = current.get("proxy-providers") or {}
        for name, provider in parsed.get("proxy-providers", {}).items():
            if provider.get("type") != "http":
                continue
            cache = provider.get("path")
            if (data.get("refresh_providers") is True or previous_providers.get(name) != provider
                    or not cache or not (MIHOMO_DIR / cache).is_file()):
                refresh_providers.add(name)
        pool = routing.pool(parsed)
        selected = pool.get('default-selected') if pool.get('type') == 'select' else None
        if selected and not refresh_providers and routing.pool(current):
            old_pool = routing.pool(current)
            previous_default = old_pool.pop('default-selected', None)
            next_default = pool.pop('default-selected')
            only_selector = parsed == current
            if previous_default is not None:
                old_pool['default-selected'] = previous_default
            pool['default-selected'] = next_default
            if only_selector:
                route = '/proxies/' + quote(routing.PROXY, safe='')
                active = json.loads(controller_request(route))
                if selected not in active.get('all', []):
                    raise ValueError('AI 默认出口已不在 Proxy 组内')
                if selected != active.get('now'):
                    controller_request(route, method='PUT', body={'name': selected})
                if previous_default != selected:
                    try:
                        state.write_config(parsed)
                    except OSError:
                        if active.get('now') != selected:
                            controller_request(route, method='PUT', body={'name': active['now']})
                        raise
                return {'ok': True, 'filename': filename, 'message': 'AI 默认出口已应用。', 'refreshed_providers': []}
        if parsed == current and not refresh_providers:
            # Do not restart proxy connections for a repeated save. Check the
            # live controller before reporting that the current config is in use.
            controller_request("/version")
            return {"ok": True, "filename": filename,
                             "message": "配置未改变，继续使用当前配置。",
                             "refreshed_providers": [], "unchanged": True}
        MIHOMO_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=MIHOMO_DIR, prefix="import-", suffix=".yaml", delete=False) as f:
            f.write(yaml.safe_dump(parsed, allow_unicode=True, sort_keys=False))
            os.chmod(f.name, 0o600)
            temp_path = Path(f.name)
        # Mihomo may remove/download incompatible geodata during -t. Validate
        # against isolated copies so rejected uploads cannot damage live assets.
        validation_dir = tempfile.TemporaryDirectory(prefix="validate-", dir=MIHOMO_DIR)
        validation_root = Path(validation_dir.name)
        resource_paths = {p.relative_to(MIHOMO_DIR) for p in MIHOMO_DIR.iterdir()
                          if p.is_file() and p.suffix.lower() in (".dat", ".mmdb")}
        for provider_key in ("proxy-providers", "rule-providers"):
            for provider in parsed.get(provider_key, {}).values():
                resource_path = Path(provider.get("path", ""))
                if str(resource_path) != "." and not resource_path.is_absolute() and ".." not in resource_path.parts:
                    resource_paths.add(resource_path)
        for resource_path in resource_paths:
            source = MIHOMO_DIR / resource_path
            if source.is_file():
                destination = validation_root / resource_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        candidate = validation_root / egress.RUNTIME_NAME
        egress.render(temp_path, candidate)
        try:
            result = subprocess.run([MIHOMO, "-t", "-d", str(validation_root), "-f", str(candidate)], capture_output=True, text=True, timeout=30,
                                    env={**os.environ, "SAFE_PATHS": str(MIHOMO_DIR.parent.resolve())})
        except subprocess.TimeoutExpired as exc:
            raise ValueError("配置校验超时，可能正在下载 GEOSITE/GEOIP 或规则库；原配置未改变") from exc
        candidate.unlink()
        if result.returncode:
            raise ValueError("Mihomo 拒绝了该配置，原配置未改变")
        if MIHOMO_CONFIG.read_bytes() != old:
            raise ConfigConflict("The configuration changed during validation. Reopen the editor.")
        backup_dir = MIHOMO_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = backup_dir / f"config-{stamp}.yaml"
        if MIHOMO_CONFIG.exists():
            shutil.copy2(MIHOMO_CONFIG, backup)
        changed_resources = {}
        proxy_cache_paths = set()
        try:
            # A reload can reuse a provider's cache even when its URL changed.
            # Save those files too: explicit refresh below may overwrite them.
            for name, provider in parsed.get("proxy-providers", {}).items():
                if provider.get("type") != "http" or not provider.get("path"):
                    continue
                destination = (MIHOMO_DIR / provider["path"]).resolve()
                if not destination.is_relative_to(MIHOMO_DIR.resolve()) or destination == MIHOMO_CONFIG:
                    raise ValueError("节点订阅缓存路径必须位于 Mihomo 数据目录内")
                previous = None
                if destination.is_file():
                    previous = backup_dir / (stamp + "-resources") / destination.relative_to(MIHOMO_DIR)
                    previous.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(destination, previous)
                    previous.chmod(0o600)
                changed_resources[destination] = previous
                if name in refresh_providers:
                    proxy_cache_paths.add(destination)
            for resource in validation_root.rglob("*"):
                if not resource.is_file() or resource.suffix.lower() in (".db", ".sqlite"):
                    continue
                relative = resource.relative_to(validation_root)
                destination = (MIHOMO_DIR / relative).resolve()
                if destination == MIHOMO_CONFIG or (destination.is_file() and filecmp.cmp(resource, destination, shallow=False)):
                    continue
                previous = None
                if destination.exists():
                    previous = backup_dir / (stamp + "-resources") / relative
                    previous.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(destination, previous)
                    previous.chmod(0o600)
                changed_resources[destination] = previous
                destination.parent.mkdir(parents=True, exist_ok=True)
                resource.chmod(0o600)
                os.replace(resource, destination)
            # Do not initialize the new subscription from the old URL's cache.
            # The rollback snapshots above retain the working copy on failure.
            for destination in proxy_cache_paths:
                destination.unlink(missing_ok=True)
            os.replace(temp_path, MIHOMO_CONFIG)
            temp_path = None
            controller_request("/configs?force=true", method="PUT", body={"path": str(MIHOMO_CONFIG)}, timeout=30)
            refreshed_providers = []
            for name, provider in parsed.get("proxy-providers", {}).items():
                if name not in refresh_providers:
                    continue
                route = "/providers/proxies/" + quote(str(name), safe="")
                try:
                    controller_request(route, method="PUT", timeout=30)
                    active = json.loads(controller_request(route))
                    count = len(active.get("proxies", []))
                    if not count:
                        raise ValueError("订阅没有返回可用节点")
                except Exception as exc:
                    raise ValueError(f"节点订阅 {name} 刷新失败") from exc
                refreshed_providers.append({"name": name, "nodes": count})
            if selected:
                controller_request('/proxies/' + quote(routing.PROXY, safe=''), method='PUT', body={'name': selected})
        except Exception as exc:
            state.atomic(MIHOMO_CONFIG,old)
            for destination, previous in changed_resources.items():
                if previous is None:
                    destination.unlink(missing_ok=True)
                else:
                    shutil.copy2(previous, destination)
            controller_request("/configs?force=true", method="PUT", body={"path": str(MIHOMO_CONFIG)}, timeout=30)
            raise ValueError(f"配置应用或节点订阅刷新失败，已恢复导入前配置：{exc}") from exc
        message = "配置已应用，变更的节点订阅已刷新。" if refreshed_providers else "配置已应用，沿用现有节点订阅。"
        return {"ok": True, "filename": filename, "message": message,
                "refreshed_providers": refreshed_providers}
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()
        if validation_dir:
            validation_dir.cleanup()
