#!/usr/bin/env python3
"""Reset local Claude Code identity while preserving MCP and shared tooling.

Reference: liseami/CCBaga bdfb90ceadfc5fae6772ffff597bddecb0b73cc3,
cleaner_config.rs and cleaner_targets.rs (MIT). Linux adaptation.
Default: preview only. Close Claude, then run reset-claude-user --apply.
No new credential backups are created. Actual project directories are untouched.
"""
# MIT License
#
# Copyright (c) 2026 CCBaga contributors
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import stat
import sys
import tempfile

ACCOUNT_KEYS = set('''
userID machineID anonymousId oauthAccount primaryApiKey additionalModelCostsCache
additionalModelOptionsAnsweredAt additionalModelOptionsCache agentLastUsed
announcementImpressions autoCompactWindowsCache cachedArtifactRoster
cachedChromeExtensionInstalled cachedDynamicConfigs cachedExperimentData
cachedExperimentFeatures cachedExtraUsageDisabledReason cachedGrowthBookFeatures
cachedGrowthBookFeaturesAt cachedStatsigGates cachedUsageUtilization changelogLastFetched
claudeAiMcpEverConnected claudeCodeFirstTokenDate clientDataCache clientDataCacheSlots
closedIssuesLastChecked customApiKeyResponses feedbackSurveyState firstStartTime
firstStartVersion githubWebConnectionStatusCache groveConfigCache hasAvailableSubscription
hasCompletedOnboarding hasOpenedAgentsView hasResetAutoModeOptInForDefaultOffer
hasSeenAutoDefaultNotice hasSeenAutoModeOutsideReadPrompt lastClawdEntranceVersion
lastOnboardingVersion lastPlanModeUse lastReleaseNotesSeen metricsStatusCache
metricsStatusCacheByPrincipal migrationVersion modelAccessCache numStartups
officialMarketplaceAutoInstallAttempted officialMarketplaceAutoInstalled
opusProMigrationComplete orgModelDefaultCache passesEligibilityCache pluginUsage
pluginUsageLspGraceAppliedIds promptQueueUseCount remoteControlUpsellSeenCount
s1mAccessCache seenNotifications skillUsage sonnet1m45MigrationComplete
subscriptionNoticeCount tipLifetimeShownCounts tipsHistory tipsHistoryByCommand
transcriptShareDismissed
'''.split())
CREDENTIAL_KEYS = {'claudeAiOauth', 'trustedDeviceToken'}
AUTH_ENV = {'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN',
            'CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR', 'ANTHROPIC_API_KEY_FILE_DESCRIPTOR'}
RESIDUE = '''projects sessions history.jsonl file-history debug plans image-cache
uploads session-env tasks shell-snapshots feedback-bundles feedback/drafts dev-mods
jobs cache telemetry statsig stats-cache.json todos usage-data usage.jsonl usage.with-fix.jsonl
paste-cache ide daemon daemon.log daemon.status.json .user-id .machine-id backups'''.split()
SHELLS = ['.profile', '.bashrc', '.bash_profile', '.bash_login', '.zshrc', '.zprofile',
          '.zshenv', '.pam_environment']


def safe(home, path):
    path = Path(path)
    if ".." in path.parts:
        raise ValueError("Parent traversal refused: " + str(path))
    path.relative_to(home)
    current = path
    while current != home:
        if current.is_symlink():
            raise ValueError('Symlink target refused: ' + str(current))
        current = current.parent
    return path


def read_json(path):
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('JSON too large: ' + str(path))
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('Expected JSON object: ' + str(path))
    return value


def clean_account(value):
    result = {k: v for k, v in value.items() if k not in ACCOUNT_KEYS}
    # Project entries contain personal sessions/usage. Keep only MCP settings.
    if 'projects' in result:
        if not isinstance(result['projects'], dict):
            raise ValueError('projects must be an object')
        projects = {}
        for name, entry in result['projects'].items():
            if not isinstance(entry, dict):
                raise ValueError('project settings must be objects')
            mcp = {k: v for k, v in entry.items() if 'mcp' in k.lower()}
            if mcp:
                projects[name] = mcp
        if projects:
            result['projects'] = projects
        else:
            result.pop('projects')
    return result


def clean_settings(value):
    result = dict(value)
    if 'env' in result:
        if not isinstance(result['env'], dict):
            raise ValueError('settings env must be an object')
        result['env'] = {k: v for k, v in result['env'].items() if k not in AUTH_ENV}
    result.pop('apiKeyHelper', None)
    return result


def clean_shell(text):
    lines = []
    for line in text.splitlines(keepends=True):
        match = re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=', line)
        if match and match[1] in AUTH_ENV:
            # A complex command could mix credentials with unrelated actions.
            # Refuse the whole plan instead of executing or partially editing it.
            raw = line[match.end():].strip()
            if (any(c in raw for c in ';`$\n&|<>')
                    or len(shlex.split(raw, comments=True)) > 1):
                raise ValueError('Complex auth assignment requires manual review')
            continue
        lines.append(line)
    return ''.join(lines)


def plan(home, config):
    changes, removals = [], []
    configs = [(home / '.claude.json', clean_account),
               (config / '.claude.json', clean_account),
               (config / '.credentials.json', lambda v: {k: x for k, x in v.items() if k not in CREDENTIAL_KEYS}),
               (config / 'settings.json', clean_settings),
               (config / 'settings.local.json', clean_settings)]
    visited = set()
    for path, transform in configs:
        safe(home, path)
        if path in visited or not path.exists():
            continue
        visited.add(path)
        before = read_json(path)
        after = transform(before)
        if before != after:
            changes.append((path, (json.dumps(after, indent=2, ensure_ascii=False)+'\n').encode()))
    for name in SHELLS:
        path = safe(home, home/name)
        if path.exists():
            before = path.read_text()
            after = clean_shell(before)
            if before != after:
                changes.append((path, after.encode()))
    candidates = [config/name for name in RESIDUE]
    candidates += [home/'.cache/claude-cli-nodejs']
    candidates += list(home.glob('.claude.json.backup*'))
    candidates += list(config.glob('.claude.json.backup*'))
    for path in candidates:
        safe(home, path)
        if path.exists() and path not in removals:
            # Only regular files/directories within the selected HOME.
            if not (path.is_file() or path.is_dir()):
                raise ValueError('Unsupported file type: ' + str(path))
            removals.append(path)
    return changes, removals


def active_claude(uid):
    for p in Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name) == os.getpid():
            continue
        try:
            if p.stat().st_uid != uid:
                continue
            comm = (p/'comm').read_text().strip().lower()
            if comm == 'claude':
                return True
            args = (p/'cmdline').read_bytes().split(b'\0')
            names = [Path(os.fsdecode(a)).name for a in args[:3] if a]
            if any(n in {'claude', 'claude.exe', 'claude.js'} for n in names):
                return True
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    return False


def atomic_write(path, data):
    old = path.stat()
    fd, temp = tempfile.mkstemp(prefix='.claude-reset-', dir=path.parent)
    try:
        os.fchmod(fd, stat.S_IMODE(old.st_mode) & 0o600)
        os.fchown(fd, old.st_uid, old.st_gid)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='permanently remove local Claude Code identity/history')
    parser.add_argument('--home', type=Path, default=Path.home(), help='target HOME; defaults to the current user')
    args = parser.parse_args()
    home = args.home.absolute()
    if '..' in home.parts or home.is_symlink() or not home.is_dir() or home.resolve() == Path('/'):
        raise ValueError('Expected a real user HOME directory')
    home = home.resolve()
    uid = home.stat().st_uid
    if os.getuid() not in (0, uid):
        raise ValueError('Run as the target user or root')
    config = Path(os.environ.get('CLAUDE_CONFIG_DIR') or str(home/'.claude'))
    if not config.is_absolute() or config == home:
        raise ValueError('CLAUDE_CONFIG_DIR must be a dedicated absolute directory inside HOME')
    safe(home, config)
    # Lock the HOME directory itself; do not create a permanent lock or backup.
    fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.apply and active_claude(uid):
            raise ValueError('Close all Claude Code processes before applying')
        if args.apply and AUTH_ENV.intersection(os.environ):
            raise ValueError('Unset inherited Claude auth variables first: ' + ', '.join(sorted(AUTH_ENV.intersection(os.environ))))
        changes, removals = plan(home, config)
        print('APPLY' if args.apply else 'PREVIEW (no changes; use --apply to execute)')
        for path, _ in changes:
            print('sanitize', path.relative_to(home))
        for path in removals:
            print('remove', path.relative_to(home))
        if args.apply:
            for path, data in changes:
                if active_claude(uid):
                    raise ValueError('Claude restarted; stopped after partial cleanup')
                safe(home, path)
                atomic_write(path, data)
            for path in removals:
                if active_claude(uid):
                    raise ValueError('Claude restarted; stopped after partial cleanup')
                safe(home, path)
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
        print(f'{len(changes)} config edits, {len(removals)} residue paths. MCP, plugins, skills, proxy settings and actual project files are preserved.')
        print('Scope: local Claude Code files in this HOME. Browser logins, remote sessions and shell history are separate.')
    finally:
        os.close(fd)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as error:
        print('Refused: '+str(error), file=sys.stderr)
        sys.exit(1)
