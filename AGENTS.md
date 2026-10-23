# Repository guide for AI assistants

This repository builds two separate services: `gateway/` and `workstation/`.
The root `compose.yaml` connects them for a Linux amd64 LAN deployment.

## Installation requests

Read [AI-INSTALL.md](AI-INSTALL.md), [README.md](README.md), and `.env.example`
before installing or changing a deployment. Inspect the actual host and existing
containers first. Use `deploy.sh` only for a new environment. Preserve existing
containers and their internal data until the user has authorized a concrete
migration or replacement plan. Do not infer permission to delete other services.

Runtime configuration, HOME and identities live inside each container. Restart
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
