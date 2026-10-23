#!/usr/bin/python3
"""Run desktop AI CLIs with account HOME and credential-free failure metadata.

Terminal streams remain attached to the existing TTY. The desktop entry holds
that terminal open after exit; no session transcript or environment is persisted.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys

TOOLS = {'codex': 'Codex CLI', 'claude': 'Claude Code'}
PROXY_KEYS = ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
              'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy')


def with_proxy_file(environment, path=Path('/etc/workstation/proxy.env')):
    """Read optional container-local proxy defaults without executing shell text."""
    updated = dict(environment)
    try:
        content = path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return updated
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].lstrip()
        key, separator, value = line.partition('=')
        key = key.strip()
        if not separator or key not in PROXY_KEYS or key in updated:
            continue
        value = value.strip()
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                continue
            value = value[1:-1]
        if '\x00' not in value:
            updated[key] = value
    return updated


def failure_log(home, tool, exit_code, environment, startup_error=None):
    directory = home / '.local/state/workstation'
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    path = directory / 'launcher-errors.jsonl'
    event = {
        'time_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'tool': tool, 'exit_code': exit_code,
        'proxy_present': {name: bool(environment.get(name)) for name in PROXY_KEYS},
    }
    if startup_error:
        event['startup_error'] = startup_error
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'a', encoding='utf-8') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(json.dumps(event, ensure_ascii=False) + '\n')
    return path


def launch(tool, arguments=()):
    if tool not in TOOLS:
        raise ValueError('Unsupported desktop CLI')
    if os.getuid() == 0:
        print('請以普通桌面使用者開啟 ' + TOOLS[tool] + '。', file=sys.stderr)
        return 1
    account = pwd.getpwuid(os.getuid())
    home = Path(account.pw_dir)
    environment = dict(os.environ, HOME=str(home), USER=account.pw_name, LOGNAME=account.pw_name)
    error_name = None
    try:
        # Read on every launch so the current desktop need not be restarted.
        environment = with_proxy_file(environment)
        project = home / 'Projects'
        project.mkdir(exist_ok=True)
        # Inherit stdin/stdout/stderr unchanged: Codex and Claude retain their TTY.
        # The installed tool wrapper applies no_new_privs before executing the CLI.
        result = subprocess.run(['/usr/local/bin/' + tool, *arguments], cwd=project, env=environment)
        exit_code = result.returncode if result.returncode >= 0 else 128 - result.returncode
    except OSError as error:
        exit_code = 127
        error_name = type(error).__name__
    if exit_code:
        print(f'\n{TOOLS[tool]} 已結束，退出碼 {exit_code}。本視窗會保留，請查看上方錯誤。', file=sys.stderr)
        try:
            path = failure_log(home, tool, exit_code, environment, error_name)
            print(f'啟動紀錄：{path}（僅退出碼、錯誤類型及代理是否設定；不含對話或憑證）。', file=sys.stderr)
        except OSError as error:
            print('啟動紀錄無法寫入：' + type(error).__name__, file=sys.stderr)
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tool', choices=TOOLS)
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    return launch(args.tool, args.arguments)


if __name__ == '__main__':
    raise SystemExit(main())
