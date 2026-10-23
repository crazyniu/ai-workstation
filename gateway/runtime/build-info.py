#!/usr/bin/env python3
"""Record a reproducible development version of the packaged gateway application.

Run after source changes and during image builds. Only packaged application
sources are read; runtime data and personal configuration are never included.
"""
import hashlib
import json
from pathlib import Path


def write_build_info(root):
    files = [root / 'components.lock.json']
    for directory, pattern in (('app', '*.py'), ('runtime', '*'), ('web', '**/*')):
        files.extend(path for path in (root / directory).glob(pattern)
                     if path.is_file())
    digest = hashlib.sha256()
    count = 0
    for path in sorted(set(files)):
        relative = path.relative_to(root)
        if relative.as_posix() == 'web/build-info.json' or any(
            part == '__pycache__' or part == '.DS_Store' or part.startswith('._')
            for part in relative.parts
        ) or path.suffix == '.pyc':
            continue
        if path.is_symlink():
            raise ValueError(f'Application source must not be a symlink: {relative}')
        digest.update(relative.as_posix().encode() + b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
        count += 1
    source_sha256 = digest.hexdigest()
    metadata = {
        'name': 'Gateway',
        'version': 'dev.' + source_sha256[:12],
        'source': 'https://github.com/crazyniu/ai-workstation',
        'source_sha256': source_sha256,
        'source_files': count,
    }
    (root / 'web/build-info.json').write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return metadata


if __name__ == '__main__':
    print(write_build_info(Path(__file__).resolve().parents[1])['version'])
