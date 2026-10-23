#!/usr/bin/env python3
"""Persistent same-origin API for the home-dev dashboard."""
import hashlib
import filecmp
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

DATA = Path(os.environ.get("DATA_DIR", "/data")) / "dashboard"
CARDS = DATA / "cards.json"
MIHOMO_DIR = Path(os.environ.get("DATA_DIR", "/data")) / "mihomo"
MIHOMO_CONFIG = MIHOMO_DIR / "config.yaml"
MIHOMO = str(Path(os.environ.get("DATA_DIR", "/data")) / "components/current/mihomo/mihomo")
MIHOMO_API = "http://127.0.0.1:9090"
import yaml

def current_secret():
    return (yaml.safe_load(MIHOMO_CONFIG.read_text()) or {}).get("secret", "")
LOCK = threading.Lock()
CONFIG_LOCK = threading.Lock()
DEFAULT_CARDS = []
GATEWAY_KEYS = ("port", "socks-port", "redir-port", "mixed-port", "external-controller", "external-ui",
                "allow-lan", "bind-address", "tproxy-port", "dns", "tun", "routing-mark", "secret", "ipv6")

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
                if not resolved.is_relative_to(MIHOMO_DIR.resolve()) or resolved == MIHOMO_CONFIG.resolve():
                    raise ValueError("订阅缓存必须位于 Mihomo 数据目录内且不能覆盖主配置")
        if kind in parsed:
            parsed[kind] = providers

def revision(content):
    return hashlib.sha256(content).hexdigest()

def read_cards():
    try:
        return json.loads(CARDS.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return [dict(card) for card in DEFAULT_CARDS]

def write_cards(cards):
    DATA.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="cards-", dir=DATA)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cards, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, CARDS)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def auth_headers():
    secret = current_secret()
    return {"Authorization": f"Bearer {secret}"} if secret else {}

def controller_request(path, method="GET", body=None, timeout=5):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(MIHOMO_API + path, data=data, method=method, headers=auth_headers())
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        return

    def reply(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def body(self, limit=8192):
        size = int(self.headers.get("Content-Length", "0"))
        if size < 0 or size > limit:
            raise ValueError("请求过大")
        data = json.loads(self.rfile.read(size) or b"{}")
        if not isinstance(data, dict):
            raise ValueError("请求必须是 JSON 对象")
        return data

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/proxy/config":
            try:
                with CONFIG_LOCK:
                    content = MIHOMO_CONFIG.read_bytes()
                self.reply(200, {"filename": "config.yaml", "content": content.decode("utf-8"),
                                 "revision": revision(content)})
            except (OSError, UnicodeError):
                self.reply(503, {"error": "Could not read the current configuration."})
            return
        if path == "/api/cards":
            with LOCK:
                self.reply(200, {"cards": read_cards()})
            return
        if path == "/api/status":
            try:
                controller_request("/version")
                state = "active"
            except Exception:
                state = "unavailable"
            self.reply(200, {"mihomo": state})
            return
        self.reply(404, {"error": "不存在的接口"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/proxy/config":
            self.import_config()
            return
        if path != "/api/cards":
            self.reply(404, {"error": "不存在的接口"})
            return
        try:
            data = self.body()
            item = self.validate_card(data)
            item["id"] = uuid.uuid4().hex
            with LOCK:
                cards = read_cards()
                cards.append(item)
                write_cards(cards)
            self.reply(201, item)
        except (ValueError, json.JSONDecodeError) as exc:
            self.reply(400, {"error": str(exc)})

    def do_PATCH(self):
        card_id = unquote(urlparse(self.path).path.removeprefix("/api/cards/"))
        if not card_id or card_id == self.path:
            self.reply(404, {"error": "页面不存在"})
            return
        try:
            item = self.validate_card(self.body())
            with LOCK:
                cards = read_cards()
                for card in cards:
                    if card.get("id") == card_id:
                        card.update(item)
                        write_cards(cards)
                        self.reply(200, card)
                        return
            self.reply(404, {"error": "页面不存在"})
        except (ValueError, json.JSONDecodeError) as exc:
            self.reply(400, {"error": str(exc)})

    def do_DELETE(self):
        card_id = unquote(urlparse(self.path).path.removeprefix("/api/cards/"))
        with LOCK:
            cards = read_cards()
            updated = [card for card in cards if card.get("id") != card_id]
            if len(updated) == len(cards):
                self.reply(404, {"error": "页面不存在"})
                return
            write_cards(updated)
        self.reply(200, {"ok": True})

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

    def import_config(self):
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            self.reply(403, {"error": "Configuration changes must come from this dashboard."})
            return
        with CONFIG_LOCK:
            self.apply_config()

    def apply_config(self):
        temp_path = None
        validation_dir = None
        try:
            data = self.body(4 * 1024 * 1024)
            content = str(data.get("content", ""))
            filename = str(data.get("filename", "config.yaml"))
            if not content or len(content.encode()) > 2 * 1024 * 1024:
                raise ValueError("配置文件为空或超过 2 MB")
            if (not 1 <= len(filename) <= 120 or Path(filename).name != filename or "\\" in filename
                    or any(ord(c) < 32 for c in filename) or not filename.lower().endswith((".yaml", ".yml"))):
                raise ValueError("只支持 .yaml 或 .yml 配置文件")
            old = MIHOMO_CONFIG.read_bytes()
            if data.get("revision") != revision(old):
                self.reply(409, {"error": "The configuration has changed. Reopen the editor before saving."})
                return
            parsed = yaml.safe_load(content)
            if not isinstance(parsed, dict) or not any(k in parsed for k in ("proxies", "proxy-providers", "proxy-groups")):
                raise ValueError("不是有效的 Mihomo 配置文件")
            validate_providers(parsed)
            current = yaml.safe_load(old)
            # Uploads change nodes and rules while keeping this gateway reachable.
            for key in GATEWAY_KEYS:
                if key in current:
                    parsed[key] = current[key]
                else:
                    parsed.pop(key, None)
            # Subscriptions may define other host overrides, but the gateway's
            # configured local name must always keep resolving to this installation.
            from state import settings, lan_ip
            hosts = parsed.setdefault("hosts", {})
            if not isinstance(hosts, dict):
                raise ValueError("hosts 必须为域名映射对象")
            hosts[settings()["domain"]] = lan_ip()
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
            try:
                result = subprocess.run([MIHOMO, "-t", "-d", str(validation_root), "-f", str(temp_path)], capture_output=True, text=True, timeout=30,
                                        env={**os.environ, "SAFE_PATHS": str(MIHOMO_DIR.parent.resolve())})
            except subprocess.TimeoutExpired as exc:
                raise ValueError("配置校验超时，可能正在下载 GEOSITE/GEOIP 或规则库；原配置未改变") from exc
            if result.returncode:
                raise ValueError("Mihomo 拒绝了该配置，原配置未改变")
            if MIHOMO_CONFIG.read_bytes() != old:
                self.reply(409, {"error": "The configuration changed during validation. Reopen the editor."})
                return
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
                for provider in parsed.get("proxy-providers", {}).values():
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
                    if provider.get("type") != "http":
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
            except Exception as exc:
                MIHOMO_CONFIG.write_bytes(old)
                for destination, previous in changed_resources.items():
                    if previous is None:
                        destination.unlink(missing_ok=True)
                    else:
                        shutil.copy2(previous, destination)
                controller_request("/configs?force=true", method="PUT", body={"path": str(MIHOMO_CONFIG)}, timeout=30)
                raise ValueError(f"配置应用或节点订阅刷新失败，已恢复导入前配置：{exc}") from exc
            self.reply(200, {"ok": True, "filename": filename, "message": "配置已应用，节点订阅已刷新",
                             "refreshed_providers": refreshed_providers})
        except Exception as exc:
            self.reply(400, {"error": str(exc) or "导入失败"})
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()
            if validation_dir:
                validation_dir.cleanup()
