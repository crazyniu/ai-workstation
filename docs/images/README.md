# Project showcase

[Gateway desktop overview](gateway-home.png) presents the forest-and-lake desktop, application icons, and grouped control-panel entries used by this project.

The image is a project showcase. The running release determines the current interface, labels, and features. It contains no account credentials and serves as presentation material; functional verification is recorded separately.

## Architecture diagram

[Workstation and gateway architecture](workstation-gateway-architecture.png) is an AI-generated diagram of the Linux LAN deployment and its optional workstation isolation. Addresses and connection directions follow the deployment configuration.

## Gateway interface captures

- [Desktop operation feedback](gateway-global-toast-desktop.jpg) shows the global toast above the gateway settings window.
- [Mobile-size operation feedback](gateway-global-toast-mobile.jpg) shows the same interface in a 390px browser responsive viewport. This capture does not represent verification on a physical phone.

- [Control panel overview](gateway-control-panel.jpg) shows the redesigned settings window at 1280 × 800: sidebar search, status cards for the gateway, Tailscale and versions, and grouped setting entries.
- [Control panel in dark mode](gateway-control-panel-dark.jpg) shows the Tailscale page with status pills and the subnet-route card.
- [Control panel at phone size](gateway-control-panel-mobile.jpg) shows the full-screen overview in a 390px browser responsive viewport.

The control-panel captures come from a local preview that runs the gateway API with simulated Tailscale, release and supervisor data; addresses use documentation ranges. The toast captures accompany the global-toast implementation in [PR #18](https://github.com/crazyniu/ai-workstation/pull/18). They illustrate the interface at that revision; validation details are recorded in the pull request.

Project and third-party artwork retain the terms described in the [root NOTICE](../../NOTICE) and [gateway NOTICE](../../gateway/NOTICE). Product names and marks belong to their respective owners.
