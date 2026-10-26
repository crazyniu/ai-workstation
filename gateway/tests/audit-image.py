#!/usr/bin/env python3
"""Stream docker save / OCI archives and audit every manifest-declared image layer.

Usage: docker image save IMAGE | python3 tests/audit-image.py
This focused check complements the Dockerfile build-context allowlist; it is not a
claim that arbitrary secrets can be detected automatically. Missing or unreadable
manifest layers fail the audit rather than silently reducing its coverage.
"""
import io
import json
import re
import sys
import tarfile

PRIVATE_STATE = re.compile(
    r'^(?:root|home/[^/]+|opt/workstation/home-template)/(?:'
    r'\.ssh/(?:id_[^/]+|authorized_keys)|'
    r'\.codex/auth\.json|\.claude/\.credentials\.json|'
    r'\.config/(?:google-chrome|chromium)/|\.git-credentials|'
    r'\.docker/config\.json|\.config/gh/hosts\.yml|'
    r'\.npmrc|\.bash_history|\.zsh_history|'
    r'\.local/share/keyrings/|\.config/tigervnc/passwd|\.vnc/passwd)'
)
SECRET_VALUE = re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-ant-[A-Za-z0-9_-]{40,})')
CREDENTIAL_ENV = {
    'DEV_PASSWORD', 'ROOT_PASSWORD', 'VNC_PASSWORD', 'GITHUB_TOKEN', 'GITHUB_PAT_TOKEN',
    'GH_TOKEN', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY',
}
GATEWAY_PRIVATE = re.compile(r'^(?:data/|var/lib/(?:mihomo|home-agent)/|opt/gateway/seed/.*(?:config\.yaml|tailscaled\.state|cards\.json|admin\.json|session-key)$)')
CREDENTIAL_ENV.update({'GATEWAY_ADMIN_PASSWORD', 'GATEWAY_CONTAINER_PASSWORD', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'})
METADATA_LIMIT = 1024 * 1024


def normalized(name):
    while name.startswith('./'):
        name = name[2:]
    return name.lstrip('/')


def audit(stream):
    failures = set()
    declared_layers = set()
    scanned_layers = set()
    failed_layers = set()
    declared_manifests = set()
    manifest_nodes = set()
    image_manifests = set()
    seen_files = set()
    declared_attestations = set()
    attestation_nodes = set()

    def blob_path(descriptor):
        digest = descriptor.get('digest', '') if isinstance(descriptor, dict) else ''
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
            failures.add('invalid or unsupported manifest descriptor digest')
            return None
        return 'blobs/sha256/' + digest.partition(':')[2]

    def metadata(name, body):
        if SECRET_VALUE.search(body):
            failures.add('credential-shaped value in image metadata: ' + name)
        try:
            document = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return False
        if name == 'manifest.json':
            if not isinstance(document, list) or not document:
                failures.add('invalid Docker save manifest.json')
            else:
                for record in document:
                    entries = record.get('Layers') if isinstance(record, dict) else None
                    if not isinstance(entries, list) or not entries:
                        failures.add('Docker manifest does not declare image layers')
                        continue
                    image_manifests.add(name)
                    for layer in entries:
                        if not isinstance(layer, str) or not layer:
                            failures.add('invalid Docker manifest layer path')
                        else:
                            declared_layers.add(normalized(layer))
        if isinstance(document, dict):
            if (document.get('_type') in ('https://in-toto.io/Statement/v1', 'https://in-toto.io/Statement/v0.1')
                    and isinstance(document.get('predicateType'), str)
                    and isinstance(document.get('subject'), list)):
                attestation_nodes.add(name)
            # Docker's containerd image store exports provenance alongside image
            # manifests. These bounded JSON statements are metadata, not tar
            # filesystem layers; all real image layers still require a full scan.
            if document.get('artifactType') == 'application/vnd.docker.attestation.manifest.v1+json':
                manifest_nodes.add(name)
                entries = document.get('layers')
                if not isinstance(entries, list) or not entries:
                    failures.add('invalid attestation manifest: ' + name)
                else:
                    for descriptor in entries:
                        if (not isinstance(descriptor, dict)
                                or descriptor.get('mediaType') != 'application/vnd.in-toto+json'
                                or not isinstance(descriptor.get('size'), int)
                                or not 0 < descriptor['size'] <= METADATA_LIMIT):
                            failures.add('unsupported or oversized attestation metadata: ' + name)
                            continue
                        path = blob_path(descriptor)
                        if path:
                            declared_attestations.add(path)
            if 'layers' in document and document.get('artifactType') != 'application/vnd.docker.attestation.manifest.v1+json':
                entries = document['layers']
                if not isinstance(entries, list) or not entries:
                    failures.add('OCI manifest does not declare image layers: ' + name)
                else:
                    manifest_nodes.add(name)
                    image_manifests.add(name)
                    for descriptor in entries:
                        path = blob_path(descriptor)
                        if path:
                            declared_layers.add(path)
            if 'manifests' in document:
                entries = document['manifests']
                if not isinstance(entries, list) or not entries:
                    failures.add('OCI index does not declare manifests: ' + name)
                else:
                    manifest_nodes.add(name)
                    for descriptor in entries:
                        path = blob_path(descriptor)
                        if path:
                            declared_manifests.add(path)
            config = document.get('config', {})
            if isinstance(config, dict):
                for item in config.get('Env', []) or []:
                    if not isinstance(item, str):
                        failures.add('invalid environment metadata: ' + name)
                        continue
                    key, _, value = item.partition('=')
                    if key.upper() in CREDENTIAL_ENV and value:
                        failures.add('credential environment baked into image: ' + key)
        return True

    def scan_layer(name, payload):
        print('AUDIT layer start: ' + name, file=sys.stderr, flush=True)
        try:
            with tarfile.open(fileobj=payload, mode='r|*') as layer:
                for member in layer:
                    path = normalized(member.name)
                    if GATEWAY_PRIVATE.search(path) and member.isfile():
                        failures.add('gateway private state in layer: ' + path)
                    if (re.search(r'(?:^|/)ssh_host_[^/]+_key$', path) or PRIVATE_STATE.search(path)) and member.isfile():
                        failures.add('private state in layer: ' + path)
                    if not member.isfile() or member.size > METADATA_LIMIT:
                        continue
                    if path.endswith(('.json', '.toml', '.env', '.yaml', '.yml', '.ini')) or path in ('etc/shadow', 'etc/gshadow'):
                        body = layer.extractfile(member).read()
                        if SECRET_VALUE.search(body):
                            failures.add('credential-shaped value in layer: ' + path)
                        if path == 'etc/shadow':
                            for line in body.decode(errors='replace').splitlines():
                                fields = line.split(':')
                                if fields[0] in ('root', 'dev') and len(fields) > 1 and fields[1] not in ('!', '!!', '*', '!*'):
                                    failures.add('unlocked password baked into layer: ' + fields[0])
            scanned_layers.add(name)
            print('AUDIT layer end: ' + name, file=sys.stderr, flush=True)
        except (tarfile.TarError, EOFError, OSError, ValueError) as error:
            failed_layers.add(name)
            print(f'AUDIT layer unreadable: {name} ({type(error).__name__})', file=sys.stderr, flush=True)

    try:
        with tarfile.open(fileobj=stream, mode='r|*') as archive:
            for entry in archive:
                name = normalized(entry.name)
                if not entry.isfile():
                    continue
                if name in seen_files:
                    failures.add('duplicate archive member prevents unambiguous audit: ' + name)
                seen_files.add(name)
                payload = archive.extractfile(entry)
                is_blob = re.fullmatch(r'blobs/sha256/[a-f0-9]{64}', name)
                if name.endswith('/layer.tar') or is_blob:
                    if is_blob and entry.size <= METADATA_LIMIT:
                        body = payload.read()
                        if body.lstrip().startswith((b'{', b'[')) and metadata(name, body):
                            continue
                        payload = io.BytesIO(body)
                    scan_layer(name, payload)
                elif name.endswith('.json'):
                    if entry.size > METADATA_LIMIT:
                        failures.add('image metadata exceeds audit size limit: ' + name)
                    else:
                        metadata(name, payload.read())
    except (tarfile.TarError, EOFError, OSError, ValueError) as error:
        failures.add('image archive unreadable: ' + type(error).__name__)
    if not image_manifests or not declared_layers:
        failures.add('no image manifest with declared layers; audit coverage cannot be established')
    for name in declared_manifests - manifest_nodes:
        failures.add('declared OCI manifest missing or unreadable: ' + name)
    for name in declared_attestations - attestation_nodes:
        failures.add('declared attestation missing or invalid JSON metadata: ' + name)
    for name in declared_layers - scanned_layers:
        state = 'unreadable' if name in failed_layers else 'missing or not a readable tar layer'
        failures.add('declared image layer ' + state + ': ' + name)
    # Reject unreadable legacy layers even if a malformed manifest omitted them.
    for name in failed_layers:
        if name.endswith('/layer.tar'):
            failures.add('unreadable image layer: ' + name)
    if failures:
        print('\n'.join(sorted(failures)), file=sys.stderr)
        return 1
    print(f'PASS: inspected all {len(declared_layers)} manifest-declared image layers for private state and baked credentials.')
    return 0


if __name__ == '__main__':
    raise SystemExit(audit(sys.stdin.buffer))
