#!/usr/bin/env python3
"""Always report PR scope; documentation-only PRs need no container builds."""
import fnmatch
import os
from pathlib import Path
import subprocess

DOCUMENTATION = (
    'README.md', 'AI-INSTALL.md', 'AGENTS.md', 'gateway/README.md',
    'workstation/README.md', 'workstation/VALIDATION.md', 'docs/**',
    'LICENSE', 'NOTICE', 'CONTRIBUTING.md', 'SECURITY.md', 'CODE_OF_CONDUCT.md',
    '.github/ISSUE_TEMPLATE/**', '.github/PULL_REQUEST_TEMPLATE.md',
)


def requires_images(paths):
    return any(not any(fnmatch.fnmatchcase(path, pattern) for pattern in DOCUMENTATION)
               for path in paths)


def main():
    build = True
    if os.environ['GITHUB_EVENT_NAME'] == 'pull_request':
        # --no-renames makes moves between code/docs inspect both sides.
        changes = subprocess.check_output([
            'git', 'diff', '--name-only', '--no-renames', '-z',
            os.environ['PR_BASE_SHA'], os.environ['PR_HEAD_SHA'], '--',
        ])
        build = requires_images(os.fsdecode(path) for path in changes.split(b'\0') if path)
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as output:
        output.write('images=' + str(build).lower() + '\n')
    print('Container builds required: ' + str(build).lower())


if __name__ == '__main__':
    main()
