#!/usr/bin/env python3
"""Export the gateway's source allowlist, never a workspace or running data."""
import argparse
import hashlib
import os
import tarfile
import tempfile
from pathlib import Path


def source_files(root, include_seed):
    files = []
    for name in (
        'Dockerfile', '.dockerignore', '.env.example', 'compose.yaml',
        'components.lock.json', 'README.md', 'NOTICE', 'PRODUCT.md',
    ):
        files.append(root / name)
    for name in ('DESIGN.md', '.impeccable/design.json'):
        if (root / name).exists():
            files.append(root / name)
    for directory, pattern in (
        ('app', '*.py'), ('runtime', '*'), ('web', '**/*'),
        ('licenses', '*'), ('scripts', '*.py'), ('scripts', '*.sh'), ('scripts', '*.cjs'),
        ('tests', '*.py'), ('tests', '*.sh'),
    ):
        files.extend(path for path in (root / directory).glob(pattern)
                     if path.is_file() or path.is_symlink())
    if include_seed:
        for component in ('mihomo', 'adguard', 'tailscale', 'panel', 'filters'):
            directory = root / 'seed' / component
            if not directory.is_dir():
                raise ValueError(f'Missing official component directory: {component}')
            files.extend(path for path in directory.rglob('*')
                         if path.is_file() or path.is_symlink())
    selected = []
    for path in sorted(set(files)):
        relative = path.relative_to(root)
        if any(part == '__pycache__' or part == '.DS_Store' or part.startswith('._')
               for part in relative.parts) or path.suffix == '.pyc':
            continue
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents
                                    if parent != root and root in parent.parents):
            raise ValueError(f'Symlinks are not allowed in source materials: {relative}')
        if not path.is_file():
            raise ValueError(f'Missing source file: {relative}')
        selected.append((path, Path('gateway-container') / relative))
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', nargs='?', default='./dist')
    parser.add_argument('--include-seed', action='store_true',
                        help='Include official component and DNS filter seed directories')
    options = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    files = source_files(root, options.include_seed)
    output = Path(options.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    name = 'gateway-source-with-seed.tar.gz' if options.include_seed else 'gateway-source.tar.gz'
    destination = output / name
    with tempfile.TemporaryDirectory(prefix='.source-export-', dir=output) as temporary:
        archive = Path(temporary) / name
        with tarfile.open(archive, 'w:gz', format=tarfile.PAX_FORMAT) as bundle:
            for path, archive_name in files:
                info = bundle.gettarinfo(str(path), arcname=str(archive_name))
                info.uid = info.gid = 0
                info.uname = info.gname = ''
                with path.open('rb') as content:
                    bundle.addfile(info, content)
        digest = hashlib.sha256()
        with archive.open('rb') as content:
            for chunk in iter(lambda: content.read(1024 * 1024), b''):
                digest.update(chunk)
        checksum = Path(temporary) / (name + '.sha256')
        checksum.write_text(f'{digest.hexdigest()}  {name}\n')
        os.replace(archive, destination)
        os.replace(checksum, output / checksum.name)
    print(f'{destination} ({len(files)} files)')


if __name__ == '__main__':
    main()
