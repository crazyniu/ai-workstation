#!/usr/bin/env python3
"""Decide which CI jobs a change needs.

Pull requests run the fast checks. They build an image only when its build
definition changes, for amd64 only. Pushes to main build every image whose
sources changed since the last published commit, on all architectures, and
re-tag the others. A `full-ci` label, a manual `full` run or a release tag
builds and verifies everything.
"""
import fnmatch
import json
import os
from pathlib import Path
import subprocess
import urllib.request

DOCUMENTATION = (
    'README.md', 'README.en.md', 'AI-INSTALL.md', 'AGENTS.md', 'gateway/README.md',
    'gateway/DESIGN.md', 'gateway/PRODUCT.md',
    'workstation/README.md', 'workstation/VALIDATION.md', 'docs/**',
    'LICENSE', 'NOTICE', 'CONTRIBUTING.md', 'SECURITY.md', 'CODE_OF_CONDUCT.md',
    '.github/ISSUE_TEMPLATE/**', '.github/PULL_REQUEST_TEMPLATE.md',
)
# Unit tests run in the fast checks and are not part of any image.
UNIT_TESTS = ('gateway/tests/test_*.py', 'workstation/tests/test-*.py')
# Everything an image is built from or verified with. Main rebuilds on these.
IMAGE_SOURCES = {'gateway': ('gateway/*',), 'workstation': ('workstation/*',)}
# What can break a build or a container start without failing a unit test.
# Pull requests build the image when one of these changes. Gateway app/ and
# web/ are covered by unit tests; most of the workstation is shell and config.
BUILD_DEFINITION = {
    'gateway': ('gateway/Dockerfile', 'gateway/components.lock.json', 'gateway/scripts/*',
                'gateway/runtime/*', 'gateway/tests/*.sh', 'gateway/tests/audit-image.py'),
    'workstation': ('workstation/*',),
}
NATIVE = ('install-native.py', 'native/*', 'tests/Dockerfile.native', 'tests/native-smoke*.sh')
WINDOWS = ('deploy.ps1', 'tests/test-deploy.ps1', 'compose*.yaml', 'scripts/ai-install-plan.py')
# This file and the workflow decide what runs, so changing them runs everything.
CI_DEFINITION = ('scripts/ci-changes.py', '.github/workflows/images.yml')

MATRIX = [
    {'component': 'gateway', 'image': 'ai-workstation-gateway', 'arch': 'amd64', 'platform': 'linux/amd64', 'runner': 'ubuntu-latest'},
    {'component': 'gateway', 'image': 'ai-workstation-gateway', 'arch': 'arm64', 'platform': 'linux/arm64', 'runner': 'ubuntu-24.04-arm'},
    {'component': 'gateway', 'image': 'ai-workstation-gateway', 'arch': '386', 'platform': 'linux/386', 'runner': 'ubuntu-24.04'},
    {'component': 'gateway', 'image': 'ai-workstation-gateway', 'arch': 'armv5', 'platform': 'linux/arm/v5', 'runner': 'ubuntu-latest'},
    {'component': 'gateway', 'image': 'ai-workstation-gateway', 'arch': 'armv7', 'platform': 'linux/arm/v7', 'runner': 'ubuntu-latest'},
    {'component': 'gateway', 'image': 'ai-workstation-gateway', 'arch': 'riscv64', 'platform': 'linux/riscv64', 'runner': 'ubuntu-latest'},
    {'component': 'workstation', 'image': 'ai-workstation', 'arch': 'amd64', 'platform': 'linux/amd64', 'runner': 'ubuntu-latest'},
    {'component': 'workstation', 'image': 'ai-workstation', 'arch': 'arm64', 'platform': 'linux/arm64', 'runner': 'ubuntu-24.04-arm'},
]
COMPONENTS = ('gateway', 'workstation')


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def requires_images(paths):
    """Whether anything beyond documentation changed."""
    return any(not matches(path, DOCUMENTATION) for path in paths)


def plan(paths, pull_request, full=False):
    """Jobs for the changed paths. paths=None means the base is unknown."""
    code = None if paths is None else [path for path in paths if not matches(path, DOCUMENTATION)]
    full = full or code is None or any(matches(path, CI_DEFINITION) for path in code)
    if full:
        build = {component: True for component in COMPONENTS}
    else:
        sources = BUILD_DEFINITION if pull_request else IMAGE_SOURCES
        build = {component: any(matches(path, sources[component]) and not matches(path, UNIT_TESTS)
                                for path in code) for component in COMPONENTS}
    # A native install copies both roles, so it follows their image inputs.
    native = full or any(build.values()) or any(matches(path, NATIVE) for path in code)
    arches = None if full or not pull_request else {'amd64'}
    matrix = [entry for entry in MATRIX if build[entry['component']] and (arches is None or entry['arch'] in arches)]
    return {
        'checks': full or bool(code),
        'gateway': build['gateway'],
        'workstation': build['workstation'],
        'images': bool(matrix),
        'matrix': {'include': matrix},
        'native': native,
        'windows': full or any(matches(path, WINDOWS) for path in code),
    }


def publishes(event, ref):
    """Only main and release tags publish images; manual runs elsewhere only verify."""
    return event != 'pull_request' and (ref == 'refs/heads/main' or ref.startswith('refs/tags/v'))


def changed(base, head):
    # --no-renames makes moves between code and docs inspect both sides.
    output = subprocess.check_output(['git', 'diff', '--name-only', '--no-renames', '-z', base, head, '--'])
    return [os.fsdecode(path) for path in output.split(b'\0') if path]


def published_base(head):
    """Head commit of the newest successful main run, which published both images."""
    url = (f"{os.environ['GITHUB_API_URL']}/repos/{os.environ['GITHUB_REPOSITORY']}"
           '/actions/workflows/images.yml/runs?branch=main&status=success&per_page=50')
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                                                   'Accept': 'application/vnd.github+json'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            runs = json.load(response)['workflow_runs']
    except (OSError, ValueError, KeyError) as error:
        print(f'Cannot read earlier runs ({error}); building everything.')
        return None
    for run in runs:
        sha = run['head_sha']
        if run['event'] in ('push', 'workflow_dispatch') and sha != head and \
                subprocess.run(['git', 'merge-base', '--is-ancestor', sha, head]).returncode == 0:
            return sha
    return None


def main():
    event, head = os.environ['GITHUB_EVENT_NAME'], os.environ['GITHUB_SHA']
    labels = os.environ.get('PR_LABELS', '').split(',')
    full = os.environ.get('FULL_RUN') == 'true' or 'full-ci' in labels or os.environ['GITHUB_REF'].startswith('refs/tags/v')
    base = ''
    if event == 'pull_request':
        paths = changed(os.environ['PR_BASE_SHA'], os.environ['PR_HEAD_SHA'])
    elif full:
        paths = None
    else:
        base = published_base(head) or ''
        paths = changed(base, head) if base else None
    result = plan(paths, event == 'pull_request', full)
    result['publish'] = publishes(event, os.environ['GITHUB_REF'])
    result['base'] = base
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as output:
        for key, value in result.items():
            output.write(f'{key}={value if isinstance(value, str) else json.dumps(value)}\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'matrix'}))
    print('Image builds:', ', '.join(f"{entry['component']}/{entry['arch']}" for entry in result['matrix']['include']) or 'none')


if __name__ == '__main__':
    main()
