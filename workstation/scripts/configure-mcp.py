#!/usr/bin/env python3
"""Add credential-free MCP defaults to a home directory, preserving user settings."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import tomllib


def servers():
    def local(name, args=None, env=None):
        result = {"command": "/usr/local/bin/workstation-mcp", "args": [name, *(args or [])]}
        if env:
            result["env"] = env
        return result
    return {
        "context7": local("context7"),
        "playwright": local("playwright", ["--executable-path", "/usr/bin/google-chrome-stable", "--headless", "--isolated", "--sandbox"]),
        "chrome-devtools": local("chrome-devtools", ["--executablePath", "/usr/bin/google-chrome-stable", "--headless", "--isolated", "--no-usage-statistics", "--no-performance-crux"]),
        "godot": local("godot", env={"GODOT_PATH": "/usr/local/bin/godot", "DISPLAY": ":1", "LIBGL_ALWAYS_SOFTWARE": "1"}),
        "github": {"url": "https://api.githubcopilot.com/mcp/"},
    }


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(text)
    try:
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def configure(home):
    defaults = servers()
    codex = home / ".codex/config.toml"
    original = codex.read_text() if codex.exists() else ""
    parsed = tomllib.loads(original)
    additions = []
    for name, server in defaults.items():
        if name in parsed.get("mcp_servers", {}):
            continue
        additions.append(f"[mcp_servers.{json.dumps(name)}]")
        for key, value in server.items():
            if key != "env":
                additions.append(f"{key} = {json.dumps(value)}")
        additions.append("startup_timeout_sec = 60")
        if name == "github":
            additions.append('bearer_token_env_var = "GITHUB_PAT_TOKEN"')
        if server.get("env"):
            additions.append(f"[mcp_servers.{json.dumps(name)}.env]")
            additions.extend(f"{key} = {json.dumps(value)}" for key, value in server["env"].items())
        additions.append("")
    if additions:
        updated = original.rstrip() + "\n\n# Workstation MCP defaults; GitHub requires your own token.\n" + "\n".join(additions)
        tomllib.loads(updated)
        atomic_write(codex, updated)
    claude = home / ".claude.json"
    config = json.loads(claude.read_text()) if claude.exists() else {}
    configured = config.setdefault("mcpServers", {})
    changed = False
    for name, server in defaults.items():
        if name in configured:
            continue
        server = dict(server)
        server["type"] = "http" if name == "github" else "stdio"
        configured[name] = server
        changed = True
    if changed:
        atomic_write(claude, json.dumps(config, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=Path.home())
    args = parser.parse_args()
    configure(args.home)
