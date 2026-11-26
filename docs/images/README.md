# Project showcase

[Niu Gateway showcase](gateway-home.png) is an AI-generated image of the gateway desktop in a browser beside a phone: the coastal wallpaper, the menu bar, the Dock with the project's app icons, and the control panel overview with its status cards. It was generated from the real captures below as references and redrawn, not composited from them.

The image is a project showcase. The running release determines the current interface, labels, and features. It contains no account credentials and serves as presentation material; functional verification is recorded separately.

## Architecture diagram

[Niu Gateway and AI Workstation architecture](workstation-gateway-architecture.png) is an AI-generated diagram of the Linux LAN deployment and its optional workstation isolation. Addresses and connection directions follow the deployment configuration.

## Gateway interface captures

- [Control panel overview](gateway-control-panel.jpg) shows the desktop at 1280 × 800: the menu bar, the Dock, and the control panel window with its unified toolbar, edge-to-edge sidebar, status cards and grouped setting entries.
- [Control panel in dark mode](gateway-control-panel-dark.jpg) shows the Tailscale page: the connection card and the device list with each device's connection path (direct or DERP relay) and traffic.
- [Proxy editor](gateway-clash-editor.jpg) shows the proxy configuration window on its 分组规则 (group rules) page: site groups with their exits, on/off switches and the fallback for other sites.
- [Account and security](gateway-password-login.jpg) shows the 账户与安全 page at 1280 × 720: the 登录需要密码 switch, the administrator password form and the current session.
- [Desktop operation feedback](gateway-global-toast-desktop.jpg) shows the notification above the Dock, clear of window toolbars.
- [Phone home screen](gateway-home-mobile.jpg) shows the 390px layout: status bar, four-column icon grid and the Dock.
- [Control panel at phone size](gateway-control-panel-mobile.jpg) shows the full-screen overview in a 390px browser responsive viewport.
- [Mobile-size operation feedback](gateway-global-toast-mobile.jpg) shows the notification in the top safe area at the same size.

All gateway captures come from a local preview that runs the gateway API with simulated Tailscale, release and supervisor data; exit addresses use documentation ranges. Phone-size captures come from a browser responsive viewport and do not represent verification on a physical phone.

Project and third-party artwork retain the terms described in the [root NOTICE](../../NOTICE) and [gateway NOTICE](../../gateway/NOTICE). Product names and marks belong to their respective owners.
