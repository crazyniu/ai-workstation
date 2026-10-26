# AI Workstation & Gateway

[![Container images](https://github.com/crazyniu/ai-workstation/actions/workflows/images.yml/badge.svg)](https://github.com/crazyniu/ai-workstation/actions/workflows/images.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

面向家庭网络与远程开发的网关与工作站环境：一个带桌面式 Web 后台的网关，一个可通过浏览器、SSH / VNC 使用的 Linux 开发工作站。

工作站默认新加坡英文，可配置国家、语言和时区。两个角色既可同机运行，也可分别部署在宿主机 A/B；独立部署入口、网络前提和初始化参数见 [AI 安装指南](AI-INSTALL.md)。

## 让 AI 帮你安装

点击下面代码块右上角的复制按钮，发送给能操作你主机的 AI 助手。也可以直接发送本仓库链接并说明“请按仓库的 AI-INSTALL.md 帮我安装”；仓库提供 [AI 安装指引](AI-INSTALL.md) 和 [Agent 入口](AGENTS.md)。

```text
请帮我安装 https://github.com/crazyniu/ai-workstation 。
先读取当前版本 README.md、AGENTS.md、AI-INSTALL.md 和 docs/platforms.md。

先只读盘点目标机器：操作系统、CPU 和用户空间架构、现有服务与数据；
使用 Docker 时核对 context、Engine 的 Linux/CPU 架构、Compose 版本和已有容器。
网关、工作站都不限定 NAS 或平台，只按各软件上游的真实支持范围选择版本；
区分 x86/32 位、amd64/x64/x86_64、arm64/aarch64、ARM 变体等。
遇到缺少上游版本的组件，说明组件名和可用方案，不套用 amd64 程序或承诺已支持。

Linux 可选择原生服务或 Docker。已有适用运行环境优先复用；
原生安装用 install-native.py，先预览再 --apply，核对发行版依赖。
Windows/macOS 使用 Docker Desktop 的 Linux containers，缺少时先完成安装；
默认 portable 端口映射，Windows 用 deploy.ps1，Linux/macOS 用 deploy.sh。
只有需要透明 LAN 网关且目标 Linux 满足 macvlan/TUN/转发条件时才选择 LAN 入口。
网关和工作站可以同机或异机；按实际网络设置代理、DNS 和客户端访问地址。
192.168.1.250/251 仅为 LAN 示例，网卡、空闲地址、路由和宿主均现场核实。

默认服务器管理员账号/密码统一 root/root；网关网页登录只需密码 root。
工作站桌面和应用使用 dev，默认密码 root，VNC 默认密码 root。
Linux 原生安装保留宿主已有 root 密码和现有 SSH 入口，不重置服务器身份。
配置保存在私有 .env 或原生初始化文件，不回显或提交个人凭据。
工作站默认 SG/en/Asia/Singapore，需要其他地区时按指南设置三项。

已有环境先说明实际状态并保留数据，不删除、重建或迁移其他服务。
Docker 数据留在容器内部，不添加业务挂载；原生状态留在文档指定目录。
不擅自迁移 Docker 存储、修改主路由器、接管宿主路由/DNS 或开放公网端口。

完成后验证实际网页登录、DNS 查询、代理请求、SSH、网页/VNC 桌面与应用启动，
核对工具 CPU/版本、重启后的数据和 SSH 指纹；需要账号登录的服务由我登录。
区分构建/健康检查、模拟执行、真实客户端验收；缺环境的项目明确标为 NOT RUN。
最后给我访问入口、账号、已通过/未验证项、服务管理命令和升级的数据注意事项。
```

![AI Workstation 与网关桌面展示](docs/images/gateway-home.png)

*项目展示图；实际界面以运行版本为准。[图片说明](docs/images/README.md)*

当前网关操作反馈的实际界面：[桌面截图](docs/images/gateway-global-toast-desktop.jpg)、[手机尺寸截图](docs/images/gateway-global-toast-mobile.jpg)。

## 支持的平台与安装方式

Linux 可选择原生服务或 Docker；Windows、macOS 使用 Docker Desktop 的 Linux 容器。两个角色按上游软件实际支持的 CPU 范围提供构建：完整工作站覆盖 amd64/x64 和 arm64；网关还覆盖 32 位 x86、ARMv5/ARMv7、RISC-V，并锁定其他上游可用架构的依赖。只有软件自身缺少对应版本时才说明限制。完整矩阵、命令和验证边界见[平台安装说明](docs/platforms.md)。

默认管理员账号、密码为 **`root / root`**；工作站应用以普通用户 `dev` 运行，默认密码和 VNC 密码均为 `root`。Linux 原生安装保留宿主已有 root 密码。默认 Docker 端口映射只绑定本机回环地址。

## 两个服务

| 服务 | 默认地址 | 能力 | 公开镜像 |
| --- | --- | --- | --- |
| Gateway | `192.168.1.250` | Mihomo / Clash、AdGuard Home、Tailscale、Web 控制面板 | `ghcr.io/crazyniu/ai-workstation-gateway` |
| Workstation | `192.168.1.251` | XFCE、Chrome、VS Code、Godot、Codex、Claude、GitHub CLI、MCP 工具 | `ghcr.io/crazyniu/ai-workstation` |

- 桌面链接支持自动获取站点 favicon，也可手动选图标；提供壁纸、主题、排序与账户设置。
- 网关内置工作站网页入口，可修改地址；内置图标与自定义链接统一排序，保存、导入和表单校验通过全局提示反馈。
- 网关默认使用密码登录，可信私网可在账户设置中关闭；工作站提供 HTTPS noVNC 网页桌面，支持双向文字剪贴板。
- 网关统一管理代理配置、DNS、子网访问、组件升级与备份恢复。
- LAN 部署中，工作站的桌面和 CLI 默认经网关代理访问外网，局域网地址绕过显式代理；bridge 部署使用配置的私有代理端点，代理留空时沿用宿主机正常出口。
- 配置、HOME 和账号身份全部保存在各自容器内部。公开镜像包含程序和默认模板，个人订阅、身份和业务数据由用户自行配置。

## 让 AI 帮你检测 IP 泄漏

复制下面的提示词，发送给能连接目标环境的 AI 助手。将示例地址替换为实际部署地址；检测结果以当次实测为准。该提示词涵盖 HTTPS 出口、STUN / WebRTC、IPv6、DNS 和 Claude 连接，并要求保留现有配置与数据。

```text
请检查本项目工作站是否存在绕过代理、暴露真实公网 IP 的情况。
目标工作站示例为 192.168.1.251，网关示例为 192.168.1.250，
实际宿主机、容器或原生服务、访问入口和预期代理出口请先现场核实。
先读取 README.md、AGENTS.md、AI-INSTALL.md 和 docs/platforms.md。
本次仅检测，保持已有服务、代理、路由、防火墙、浏览器配置和用户数据原状；
使用当前可用的原生工具操作桌面和浏览器，确认测试运行在目标工作站。

1. 盘点实际网络：记录接口、地址、默认路由、策略路由、DNS、代理环境变量，
   以及浏览器、Claude Desktop / Claude Code 的运行状态与适用代理策略。
   区分工作站、网关、宿主机和控制端，核对多网卡、Docker / VPN 等额外路径。

2. 在工作站通过两个独立 HTTPS 查询服务测出口 IP，区分系统默认路径和
   应用实际使用的代理路径。与预期代理出口、可安全取得的宽带出口基线比较，
   并结合实时转发链判断；仅看到两个查询结果相同，证据仍不完整。

3. 从工作站实际发送 STUN Binding 请求，至少测试 Google STUN 的 19302
   和 Cloudflare STUN 的 3478 端口。记录当次解析地址，校验响应事务 ID，
   读取映射公网地址；对各可用接口分别检测。保持测试连接一段时间，
   同步核对网关实时连接的源 IP、协议、目标、命中规则和代理链。

4. 在目标工作站的实际浏览器中执行 WebRTC ICE 候选收集，记录浏览器版本、
   代理与 WebRTC 策略，区分 host、srflx、relay、mDNS、私网地址和公网地址。
   将候选中的公网 IPv4 / IPv6 与 HTTPS 出口、预期代理出口逐项比较。
   网络层 STUN 探测和浏览器完整 WebRTC 测试分别报告；缺少浏览器访问时，
   浏览器项记为 NOT RUN，同时继续完成可执行的网络检查。

5. 检查公网 IPv6 地址、IPv6 路由、DNS 的实际解析路径和 UDP/443 的转发链。
   有 IPv6 时分别验证其出口；DNS 结合查询、日志或限定范围的抓包取证，
   系统配置和检测页的解析服务商标签只作线索。区分 DNS 泄漏与公网 IP 泄漏。

6. 对正在运行的 Claude 及其子进程观察网络连接，记录观察时长、采样方式，
   尽量通过 PID、socket、源端口和时间关联转发记录。区分主动测试产生的
   STUN 请求与应用自身活动；未观察到连接仅代表观察窗口内的结果。
   登录、语音等未触发场景单列为未验证，记录需要用户配合的具体步骤。

7. 检查规则顺序、子规则、源地址强制代理、UDP 支持和直连回退策略。
   特别确认前面的工作站子规则是否优先于后面的通用 STUN / QUIC 拒绝规则。
   区分“已拦截”“经预期代理转发”“绕过代理直连”；STUN 可连通本身不能
   证明泄漏，超时也不能单独证明拦截。代理故障时的行为仅检查现有证据，
   停服务或切换出口的故障演练另列为未验证。

最后输出检测表：检查项、实际结果、关键证据、PASS / FAIL / NOT RUN，
并给出“确认泄漏 / 本次未发现泄漏 / 证据不足”的结论和适用范围。
发现问题时定位具体路径、规则与影响，并给出最小修复建议。
保留私有检测报告；公开文档使用脱敏示例，凭据、个人配置和原始日志留在私有位置。
```

## 每个容器的软件

以下清单对应仓库的镜像构建定义。固定版本以 [网关组件锁定文件](gateway/components.lock.json)、[工作站版本文件](workstation/versions.env) 和 [MCP 依赖锁定文件](workstation/mcp/package-lock.json) 为准；通过 Debian/Ubuntu APT 安装的软件版本由构建时的软件源决定。

### `192.168.1.250`：Clash 网关

| 类别 | 安装的软件 |
| --- | --- |
| 代理与面板 | Mihomo `1.19.33`、MetaCubeXD `1.273.1` |
| DNS 与过滤 | AdGuard Home `0.107.79`、内置 AdGuard DNS filter 规则快照 |
| 远程网络 | Tailscale `1.104.2` |
| Web 后台 | 项目网关桌面、WinBox `0.2.82`、CodeMirror YAML 编辑器 |
| 系统与运行时 | Ubuntu `24.04`、发行版系统 Python 3 / PyYAML、Nginx、Supervisor、Tini |
| 管理工具 | OpenSSH Server、Git、GitHub CLI、curl、DNS 查询及路由/防火墙工具 |

### `192.168.1.251`：Claude 开发工作站

| 类别 | 安装的软件 |
| --- | --- |
| 桌面与连接 | Debian `13`、XFCE、Thunar 文件管理器、XFCE Terminal、TigerVNC、noVNC `1.7.0`、websockify、OpenSSH Server |
| 浏览器与编辑器 | Google Chrome `156.0.8078.47`、Visual Studio Code `1.143.1`、Godot `4.7.2` |
| AI CLI | Codex `0.164.0`、Claude Code `2.1.309` |
| 开发运行时 | Python 3（Ubuntu 软件包，`3.14` 系列）、Node.js `24.22.1`、npm / npx、GCC |
| 开发与进程管理 | Git、GitHub CLI、curl、Supervisor；Ubuntu 系统 Python `3.14` 用于系统服务 |
| 本地 MCP | Context7 `4.4.4`、Playwright `0.0.83`、Chrome DevTools `1.12.0`、Godot MCP `0.1.1`、Unity MCP `10.3.0` |
| 远程 MCP | GitHub MCP 连接配置，使用个人账号授权 |
| 可选 Unity 环境 | Unity Editor `6000.3.27f1`（6.3 LTS）、Hub `3.22.4`；使用 Unity Personal 免费许可证，安装方式见 [Unity 说明](workstation/unity/README.md) |

工作站通过 `python3` 使用 Ubuntu 提供的 Python `3.14` 系列，补丁版本随系统软件包更新。MCP 配置同时提供给 Codex 和 Claude，浏览器工具使用容器内的 Chrome。详细清单与使用方式见 [工作站说明](workstation/README.md)。

## 首次部署

默认 portable 模式适用于 Linux、Windows、macOS 的 Docker Linux 容器；需要 Docker Compose 2.33.1+。首次部署：

```sh
git clone https://github.com/crazyniu/ai-workstation.git
cd ai-workstation
cp .env.example .env
chmod 600 .env
./deploy.sh
```

Windows PowerShell 执行 `Copy-Item .env.example .env` 后运行 `.\deploy.ps1`。默认入口为网关 `http://127.0.0.1:8080/`、工作站 `https://127.0.0.1:6080/`，SSH 分别为 2223/2222。默认管理员均为 `root / root`。

Linux 不安装 Docker 时使用 `python3 install-native.py` 预览，再按[原生安装流程](docs/platforms.md#linux-原生安装)执行。需要独立 LAN 地址和透明网关时使用下面的 Linux macvlan 入口，现场确认网卡、地址、TUN 和转发能力。

首次部署入口发现本项目已有容器（包括停止的容器）会退出，保留内部数据。后续操作继续指定本次选择的 Compose 文件；portable 模式使用 `docker compose --env-file .env -f compose.portable.yaml restart`。

### 按宿主机选择部署入口

工作站 251 可以位于宿主机 A，网关 250 可以位于宿主机 B。每台机器分别保存仓库和私有 `.env`，独立设置本机网卡、网络、密码与镜像版本。

| 部署方式 | 首次创建命令 | Compose 文件 |
| --- | --- | --- |
| 通用 Docker 端口映射 | `./deploy.sh` / `.\deploy.ps1` | `compose.portable.yaml` |
| 同一 Linux 宿主机、同一 LAN | `./deploy.sh all` | `compose.yaml` |
| 宿主机 B：独立网关 | `./deploy.sh gateway` | `compose.gateway.yaml` |
| 宿主机 A：同一 LAN 的工作站 | `./deploy.sh workstation` | `compose.workstation.yaml` |
| 宿主机 A：跨网段或 VPN 的工作站 | `./deploy.sh workstation-bridge` | `workstation/compose.yaml` |

分开部署时先验收 B 的网关，再部署 A 的工作站。同一 LAN 的两个角色使用各自宿主机的 `LAN_INTERFACE`，通过实际 LAN 地址通信。跨网段时，在 A 的 `.env` 中将 `WORKSTATION_HTTP_PROXY` 和 `WORKSTATION_HTTPS_PROXY` 指向已确认可达的网关私有代理端点；该模式保留 A 的正常路由，DNS、UDP 与整机出口按实际网络单独配置。bridge 的 SSH/VNC 默认绑定 A 的 `127.0.0.1`，通过到 A 的 SSH 隧道访问。

后续操作使用本次实际选定的 Compose 文件，例如在宿主机 A 的同 LAN 工作站部署目录中：

```sh
docker compose --env-file .env -f compose.workstation.yaml ps
docker compose --env-file .env -f compose.workstation.yaml restart workstation
```

网关部署使用 `compose.gateway.yaml`；bridge 工作站使用 `workstation/compose.yaml`。独立入口通过网络连接远端网关，无需在 A 上同时运行 gateway 容器。各拓扑的前提与检查步骤见 [AI 安装指南](AI-INSTALL.md#0-先确定角色宿主机和网络拓扑)。

### 浏览器桌面与复制粘贴

工作站同时提供 VNC 和 noVNC 网页入口，访问 `https://工作站地址:6080/` 自动进入同一个 XFCE 桌面。通过左侧剪贴板面板双向传递中文和多行文字。首次启动生成容器内部的 HTTPS 证书，重启沿用；自签名证书首次访问需要在浏览器确认。bridge 入口仅映射宿主 `127.0.0.1:6080`，可通过 SSH 隧道使用。

可信内网需要免证书提示时，显式设置 `NOVNC_TLS=0`，改用 `http://工作站地址:6080/`；配合 `VNC_AUTH=none` 即为免密码 HTTP 桌面。此连接不加密，文字通过 noVNC 左侧剪贴板面板传递；依赖安全上下文的浏览器 API 会受限。默认仍为 `NOVNC_TLS=1` 的 HTTPS。自定义 `NOVNC_ALLOWED_ORIGINS` 必须与实际入口的协议和端口一致。

默认 `VNC_AUTH=password`，网页使用已有 VNC 密码。用户明确选择可信私网免密码时，在新建容器的私有 `.env` 设置 `VNC_AUTH=none`；这同时关闭网页和原生 VNC 的密码认证，SSH 仍使用自己的认证。能访问该端口的设备可以操作桌面，因此不要为免密码入口配置公网映射。网页不保存或嵌入 VNC 密码。

默认仅允许工作站自身 IP、hostname 和 localhost 对应协议的 WebSocket 来源；使用自定义域名、反向代理或不同外部端口时，设置 `NOVNC_ALLOWED_ORIGINS` 为实际入口来源，多个值用空格分隔。已有部署先保留内部数据，按实际运行入口配置服务；不要为添加网页桌面直接重建有数据的容器。

### 工作站国家、语言和时区

初始化默认使用新加坡英文，私有 `.env` 中对应参数为：

```dotenv
WORKSTATION_COUNTRY=SG
WORKSTATION_LANGUAGE=en
WORKSTATION_TIMEZONE=Asia/Singapore
```

国家使用大写两位代码，语言使用小写语言代码，两者通常组合为 `en_SG.UTF-8`；时区独立使用 IANA 名称。例如台湾繁体中文为 `TW / zh / Asia/Taipei`，美国英文（纽约）为 `US / en / America/New_York`。台湾英语使用 `TW / en / Asia/Taipei`：英语界面采用 `en_US.UTF-8`，台湾日期、货币等地区格式采用 `zh_TW.UTF-8`，无需不存在的 `en_TW`。初始化按需生成所需 locale，并将配置应用到 SSH 登录和 XFCE 会话。

已有容器可通过内部 `/etc/workstation/region.json` 覆盖地区配置，再重启同一容器；提供的字段优先于容器环境变量。修改 `.env` 后重启不会更新已有容器的环境变量定义。配置文件写法、参数校验和验收命令见 [AI 安装指南](AI-INSTALL.md#21-工作站国家语言和时区初始化)。地区设置控制容器内部语言、格式和时间，公网出口由网关和代理配置决定。

地区初始化功能要求所选镜像包含 `/etc/workstation/region.py`。当前源码的验证与公开镜像发布状态见 [验证记录](workstation/VALIDATION.md)；部署前核对实际镜像版本。

### 重置 Claude 用户信息

工作站镜像安装 `reset-claude-user` 命令，在 251 的普通用户 `dev` 终端运行：

```sh
reset-claude-user          # 预览清理项目，不修改文件
reset-claude-user --apply  # 关闭 Claude 后，执行本地身份与历史清理
```

清理 Claude Code 登录凭据、用户/设备标识、会话、输入历史、日志及旧配置备份；保留当前 MCP 配置、MCP OAuth 凭据、插件、技能、通用代理设置及实际项目文件。只修改选定 HOME 中的 Claude 数据及独立的认证变量声明，不清理浏览器登录、远端会话或共享 Shell 历史。执行时检查 Claude 进程及继承的认证环境变量，发现仍在使用的身份时拒绝清理。清理按需手动执行，容器启动不会自动重置账号。

命令随包含本次脚本的新镜像提供。完整范围、从宿主机执行的命令及验证方法见 [AI 安装指南](AI-INSTALL.md#22-手动重置-claude-code-用户信息)。

### LAN 访问入口

网关桌面内置“工作站”图标，默认打开 `https://192.168.1.251:6080/`，与工作站镜像默认协议一致。在“设置 → 桌面管理”或右键图标的“设置入口地址”中修改实际 IP、域名、协议和端口；可信内网 HTTP 服务填写对应的 `http://` 地址。全部内置图标和自定义链接均可拖拽排序，选中图标后也可用 `Alt + ↑ / ↓` 调整。地址和顺序保存在网关内，刷新、重启及换浏览器后沿用，并包含在配置备份中。

| 入口 | 初始账号 / 密码 |
| --- | --- |
| 网关 Web：`http://192.168.1.250/` | 密码来自 `WEB_PASSWORD`，示例值为 `root` |
| 网关 SSH：`192.168.1.250:22` | `GATEWAY_USER` / `GATEWAY_PASSWORD`，示例均为 `root` |
| 工作站 SSH：`192.168.1.251:22` | 管理员 `root / root`；应用用户 `dev / root` |
| 工作站 VNC：`192.168.1.251:5901` | `VNC_PASSWORD`，示例值为 `root` |

部署前设置自己的密码。VNC 密码接受 1–8 个 ASCII 字符；Compose 默认启用工作站 root / root 管理登录，桌面应用仍由 dev 运行。网关 Web 密码首次初始化后由“设置 → 账户”管理。后续环境变量变更与数据处理见各服务文档。

可信私网可在“设置 → 账户 → 密码登录”关闭“进入网关时需要密码”，输入当前密码后保存。关闭后，能访问网页的设备可直接管理网关、Clash 和 AdGuard Home；SSH 认证独立保留。重新开启仍需当前密码。登录开关和原密码保存在网关内部，重启沿用，均不随网页配置备份导出或恢复。全新容器默认开启密码登录，详见[网关账户说明](gateway/README.md#首次设置与日常使用)。

## 开始使用

1. 打开网关主页，在代理配置中导入自己的 Clash / Mihomo YAML 并应用，通过 Clash 面板选择节点。
2. 让客户端使用网关 DNS 后，通过 `http://home.arpa` 访问主页。需要代理整个设备时，同时将该设备的默认网关设为网关容器地址。
3. 在 Tailscale 设置中登录自己的账号，并按页面提示批准子网路由。
4. 点击网关“工作站”图标或通过 VNC 打开桌面，也可通过 SSH 登录 `dev`。在应用内完成 Codex、Claude、GitHub 等个人账号登录。

```sh
docker compose ps
docker compose logs --tail 100 gateway
docker compose exec --user 1100:1100 -e HOME=/home/dev workstation gh auth login
```

更多配置见 [网关使用说明](gateway/README.md) 和 [工作站使用说明](workstation/README.md)。

## 数据与升级

Docker 部署的两个服务不声明业务 bind mount、命名卷或匿名卷。数据写入容器层，底层位置由宿主的 Docker `data-root` 决定；建议放在 SSD，Compose 本身不会迁移宿主存储。

原生安装的状态与服务管理见[平台说明](docs/platforms.md#linux-原生安装)。

**重启保留数据；删除或重新创建容器会丢失内部数据。** 替换镜像前，先停止业务、导出需要保留的私有状态，并验证恢复流程。完整私有镜像用于原环境恢复；升级到新镜像需要选择性迁移配置和用户数据。操作步骤见 [网关数据处理](gateway/README.md) 和 [工作站备份与恢复](workstation/README.md)。个人状态、恢复镜像和凭据应留在私有存储中。

网关 Web 内的组件升级会保留 `/data` 中的配置，失败时回退组件。后台代码、Nginx、Python 与基础系统通过替换镜像更新。

## 开发与验证

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install PyYAML
python3 -m unittest discover -s gateway/tests -v
python3 -m unittest discover -s tests -p 'test_*.py' -v
for test in workstation/tests/test-*.py; do python3 "$test"; done

python3 gateway/scripts/fetch-components.py amd64
docker build --platform linux/amd64 -t gateway-local:test gateway
bash gateway/tests/clean-smoke.sh gateway-local:test
docker image save gateway-local:test | python3 gateway/tests/audit-image.py

docker build -t workstation-local:test workstation
bash workstation/tests/smoke.sh workstation-local:test
bash workstation/tests/internal-storage.sh workstation-local:test
bash workstation/tests/web-desktop.sh workstation-local:test
docker image save workstation-local:test | python3 workstation/tests/audit-image.py
```

容器验证需要 Linux Docker 环境。GitHub Actions 按 CPU 架构构建两个角色的干净镜像，运行启动、内部存储、原生安装和镜像层检查；主分支验证通过后发布 `latest` 与 `sha-<完整提交号>` 标签。使用固定 SHA 标签可选择已验证的版本。实时进度见 [Actions](https://github.com/crazyniu/ai-workstation/actions/workflows/images.yml)。

默认分支通过 PR 和 `Required checks` 合并门槛保护，要求分支保持最新、审查讨论已解决，并禁止强推和删除。代码 PR 验证两个镜像；纯文档 PR 执行轻量检查并报告同一个必过结果。规则说明见 [贡献指南](CONTRIBUTING.md#默认分支保护)，版本化定义见 [main Ruleset](.github/rulesets/main.json)。

| 路径 | 内容 |
| --- | --- |
| [`gateway/`](gateway/) | Web 后台、网关运行时、组件锁定文件和测试 |
| [`workstation/`](workstation/) | 桌面环境、工具安装、启动配置和测试 |
| [`compose.portable.yaml`](compose.portable.yaml) | Linux / Windows / macOS 通用 Docker 部署 |
| [`install-native.py`](install-native.py) | Linux 原生安装、冲突检查和服务注册 |
| [`docs/platforms.md`](docs/platforms.md) | 平台、CPU、默认账号与安装选择 |
| [`compose.yaml`](compose.yaml) | Linux LAN 双容器网络与运行参数 |
| [`compose.gateway.yaml`](compose.gateway.yaml) | 宿主机 B 的独立网关部署 |
| [`compose.workstation.yaml`](compose.workstation.yaml) | 宿主机 A 的同 LAN 工作站部署 |
| [`workstation/compose.yaml`](workstation/compose.yaml) | 跨网段私有代理或独立 bridge 工作站部署 |
| [`AI-INSTALL.md`](AI-INSTALL.md) | 面向 AI 的拓扑选择、初始化、迁移和验收指南 |
| [`tests/`](tests/) | 部署入口保护测试 |
| [`docs/`](docs/) | 项目展示素材与来源说明 |

欢迎提交问题和 Pull Request。开发约定见 [CONTRIBUTING.md](CONTRIBUTING.md)，漏洞报告见 [SECURITY.md](SECURITY.md)。

## 许可

仓库自有代码采用 [MIT License](LICENSE)。第三方组件、字体、编辑器依赖及随镜像安装的软件按各自许可分发；MIT 不替代这些许可。来源与素材说明见 [NOTICE](NOTICE) 和 [网关第三方清单](gateway/NOTICE)。
