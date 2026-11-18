# Repository guide for AI assistants

This repository builds two separate services: `gateway/` and `workstation/`.
`compose.portable.yaml` is the default manual Docker deployment on Linux, Windows and
macOS; `deploy.ps1` is the Windows entry. Linux may also install native services
using `install-native.py` (preview first). Read `docs/platforms.md` for the vendor
architecture matrix, native prerequisites and validation boundaries. Do not
restrict either role to NAS or amd64 beyond actual upstream software support.
The root `compose.yaml` connects them for an explicit Linux LAN deployment.
`compose.gateway.yaml` and `compose.workstation.yaml` deploy roles independently
on separate hosts on the same LAN. For routed/private-proxy access, the
workstation bridge example is `workstation/compose.yaml`. Read AI-INSTALL.md to
select the actual topology; do not assume both roles share a Docker host.
The workstation defaults to Singapore/English and supports country, language
and timezone initialization through WORKSTATION_* settings or internal
`/etc/workstation/region.json`.

For Linux LAN deployments the workstation role includes `workstation-network`.
This helper uses the workstation image and holds its LAN address and firewall
capability. Keep the desktop in that namespace with NET_ADMIN and NET_RAW
dropped. Preserve the editable Clash source and compile the enforced runtime
policy on startup, reload and restore. The helper contains no user data.

## Installation requests

For each new AI installation, ask the user to confirm the country before deploying. Pass that answer through `AI_INSTALL_COUNTRY`. SG uses English and Asia/Singapore, TW uses Traditional Chinese and Asia/Taipei, and US uses English and America/Los_Angeles. Preserve existing region settings on upgrades.

Each AI request installs or upgrades only the named role. For a new gateway at
`192.168.1.250`, run `./deploy.sh ai gateway` with
`ghcr.io/crazyniu/ai-workstation-gateway:latest`. For a new workstation at
`192.168.1.251`, run `./deploy.sh ai workstation` with
`ghcr.io/crazyniu/ai-workstation:latest`. Use the published project image and
its shipped services. Do not install additional software or substitute images,
IP addresses, host packages or deployment modes. Report any blocking conflict.
For an upgrade, identify the existing target, back up its private state and
follow the role-specific migration procedure in AI-INSTALL.md.

Read [AI-INSTALL.md](AI-INSTALL.md), [README.md](README.md), and `.env.example`
before installing or changing a deployment. Inspect the actual host and existing
containers first. Use `deploy.sh` only for a new environment. Preserve existing
containers and their internal data until the user has authorized a concrete
migration or replacement plan. Do not infer permission to delete other services.

Docker runtime configuration, HOME and identities live inside each container.
Native state uses the dedicated directories in docs/platforms.md; preserve host
root credentials, SSH/nginx configuration and existing services. Default new
container administrator credentials are root/root. Workstation desktop credentials are dev/dev. Gateway Web and workstation VNC use the password root. Restart
preserves them; deletion or recreation removes them. Do not add business bind
mounts or data volumes to the default deployment. Keep credentials, personal
configuration, logs and private snapshots outside Git and public images.

## Source changes

Use the checks listed in README.md and CONTRIBUTING.md. Changes to packaged
gateway sources require regenerating `gateway/web/build-info.json` with
`python3 gateway/runtime/build-info.py`. Keep component versions and checksums
explicit. Public images must build from source and clean upstream artifacts.

Report what was actually verified, including untested login, client or network
paths. A build or health check alone does not prove the complete user workflow.

## Pull request delivery

The repository has GitHub auto-merge enabled. For authorized development work,
enable squash auto-merge immediately after creating a non-draft pull request:
`gh pr merge <number> --auto --squash --match-head-commit <head-sha>`.
Resolve prerequisite PRs in dependency order, target the latest `main`, and keep
all required checks and branch protection in force. Follow CI through completion,
fix failures, and verify the PR's merged state and final commit. Creating a PR or
enabling auto-merge alone does not complete delivery.
