#!/bin/sh
# Export an already-built clean image; never export the running container.
set -eu
image=${GATEWAY_IMAGE:-gateway-local:1.0.0}
out=${1:-./dist}
arch=$(docker image inspect --format '{{.Architecture}}' "$image")
if [ "$arch" != amd64 ]; then
  echo 'The initial offline bundle supports amd64 only.' >&2
  exit 1
fi
mkdir -p "$out"
name=gateway-local-1.0.0-amd64.tar.gz
staging=$(mktemp -d "$out/.export-XXXXXX")
trap 'rm -rf "$staging"' EXIT HUP INT TERM
# Keep save and gzip separate so a failed docker save cannot produce a success.
docker image save --output "$staging/image.tar" "$image"
gzip -c "$staging/image.tar" > "$staging/$name"
(
  cd "$staging"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$name" > "$name.sha256"
  else
    shasum -a 256 "$name" > "$name.sha256"
  fi
)
mv "$staging/$name" "$staging/$name.sha256" "$out/"
echo "$out/$name"
