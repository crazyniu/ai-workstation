# 平台、架构与安装方式

本项目的两个角色均不限定 NAS 或某种品牌设备。以各组件的上游支持范围为准：支持目标系统和 CPU 的软件使用原生版本；缺少上游版本时，报告具体组件及替代方案，不把安装脚本中的旧限制当成产品限制。

## 系统与运行方式

| 宿主系统 | Docker | 不安装 Docker |
| --- | --- | --- |
| Linux：服务器、PC、云主机、开发板、NAS | Docker Engine + Compose；默认端口映射，可选 LAN macvlan | 原生 Linux 服务；自动安装入口适配 Debian 12+、Ubuntu 24.04+，需要 Python 3.11+ 和 systemd。其他发行版可自行准备依赖或使用 Docker |
| Windows | Docker Desktop，启用 Linux containers；PowerShell 安装入口 | 项目部署使用 Docker；不提供 Windows 原生服务 |
| macOS：Intel / Apple Silicon | Docker Desktop；自动选取对应 Linux CPU 镜像 | 项目部署使用 Docker；不提供 macOS 原生服务 |

Windows/macOS 的 Docker 内运行 Linux 用户空间。Docker Desktop 不支持本项目原来的 macvlan LAN 拓扑，因此默认使用 bridge 和端口映射；这不是网关或工作站的平台限制。[Docker 官方 macvlan 说明](https://docs.docker.com/engine/network/drivers/macvlan/)。Linux 透明网关需要 TUN、转发权限及实际 LAN 路由，单独选择 LAN 模式。

## CPU 与组件

`x64` / `x86_64` / `amd64` 表示同一类 64 位 x86；`x86` / `i386` / `i686` 表示 32 位 x86；`aarch64` / `arm64` 表示 64 位 ARM。以 Docker Engine 的架构或 Linux 用户空间架构选择文件，不只检查运行安装命令的电脑。

| CPU | 网关 | 完整工作站 | 上游差异 |
| --- | --- | --- | --- |
| amd64 / x64 | 构建、运行检查与发布矩阵 | 构建、运行检查与发布矩阵 | Chrome、VS Code、Codex、Claude、Godot；Unity Linux Editor/Hub 按需安装 |
| arm64 / aarch64 | 同上 | 同上 | Linux Google Chrome 没有 ARM64 包，改用 Chromium；VS Code、Codex、Claude、Godot 和 Unity MCP 使用 ARM64 依赖。Unity Linux Editor/Hub 的现有固定版本仅提供 amd64，需在其他支持的机器上运行 Editor |
| 32 位 x86 / 386 | 构建、运行检查与发布矩阵 | 当前固定版本的 Codex、Claude 没有 32 位 Linux 二进制 | 安装器说明缺少的上游组件，不静默装入 amd64 程序 |
| ARMv5、ARMv7 | 网关构建、运行检查与发布矩阵 | 同上，Codex、Claude 缺少对应二进制 | 必须使用正确 ARM 变体；ARMv6 的组件已锁定，可在兼容基础系统上原生安装或自行构建 |
| RISC-V 64 | 网关构建、运行检查与发布矩阵 | 当前 Codex、Claude 无对应固定发布 | 网关使用 Mihomo、AdGuard Home、Tailscale 的 riscv64 文件 |
| MIPS / MIPSLE / MIPS64 / MIPS64LE | 三个网关组件均有锁定文件，可使用兼容 Linux 的原生安装或自备基础镜像 | 受工作站上游组件发布范围限制 | 当前公共 Debian 镜像不提供这些变体；没有将它们加入 Docker 发布矩阵。安装环境需有 Python 3.11+、APT 依赖和对应 ABI |
| 其他 CPU | 按所选版本逐组件检查 | 按所选版本逐组件检查 | 例如部分网关组件没有 ppc64le、s390x、LoongArch 发布，不能承诺完整组合运行 |

以上“矩阵”是 CI 必须执行的检查定义；某个提交是否通过、镜像是否已发布，分别以该提交 Actions 和 GHCR manifest 为准。其他架构的锁定文件是构建输入，不是实机验收证据。网关锁文件包含各架构的固定版本、官方地址与 SHA256；工作站版本文件包含两种 CPU 的独立校验值。APT 提供的 Chromium 与基础系统包随软件源更新，实际版本在验收时输出。

## 通用 Docker 安装

先安装并启动 Docker Engine / Docker Desktop，核实当前 context 指向目标主机、Engine 为 Linux，Compose 版本至少 2.33.1。首次安装：

```sh
cp .env.example .env
chmod 600 .env
# Linux / macOS；默认 portable，也可显式传 portable
./deploy.sh
# 仅网关，包括没有工作站上游二进制的 32 位主机
./deploy.sh gateway-portable
# 仅工作站，按 .env 设置可选的私有网关代理
./deploy.sh workstation-bridge
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
.\deploy.ps1
# 仅网关：.\deploy.ps1 -Role gateway-portable
# 仅工作站：.\deploy.ps1 -Role workstation-bridge
```

Windows 的 `.env` 继承当前用户目录的 ACL，应保存在私人目录中。所有入口检查本 Compose 项目中运行和停止的容器，发现已有容器即停止首次部署。端口映射默认绑定 `127.0.0.1`：

| 服务 | 默认入口 | 默认账号 / 密码 |
| --- | --- | --- |
| 网关网页 | `http://127.0.0.1:8080/` | 管理员 `root`，页面只输入密码 `root` |
| 网关 SSH | `ssh -p 2223 root@127.0.0.1` | `root / root` |
| 工作站 SSH 管理 | `ssh -p 2222 root@127.0.0.1` | `root / root` |
| 工作站普通用户 | 同一 SSH 端口，用户名 `dev` | `dev / root` |
| 工作站网页桌面 | `https://127.0.0.1:6080/` | VNC 密码 `root` |
| 工作站 VNC | `127.0.0.1:5901` | VNC 密码 `root` |
| HTTP / HTTPS 显式代理 | `127.0.0.1:7890` | 从网关网页导入用户自己的代理配置 |
| AdGuard DNS | `127.0.0.1:1053`，TCP / UDP | 非标准 DNS 端口；客户端须支持指定端口 |

网关容器 root HOME 使用 `/data/home`，包含在网关数据备份范围内。默认管理员凭据统一为 **`root / root`**，供首次初始化使用。桌面、Codex、Claude、浏览器仍由 `dev` 执行，其默认密码同为 `root`。在开放 LAN 或公网访问之前配置私有密码；示例默认不开放公网。已有部署的网关账户和密码保留，不因文档默认值变化自动重置。工作站密码环境变量属于每次启动输入，按原部署配置保留。

需要 LAN 访问时，明确设置 `BIND_ADDRESS`、对应端口和宿主防火墙，并使用可达的宿主 IP；不把容器私有 IP 写成客户端访问地址。自定义网页桌面端口或域名要设置实际的 `NOVNC_ALLOWED_ORIGINS`。portable 网关使用 Tailscale userspace 模式，不向宿主添加透明路由，也不接管宿主 DNS；需要透明网关 / Tailscale 子网路由时使用满足网络权限要求的 Linux LAN 部署。默认 workstation 经同一 Compose 的 `gateway:7890` 显式代理；HTTP 代理不覆盖全部 UDP 或系统 DNS。

Linux LAN 部署继续使用 `./deploy.sh all`、`./deploy.sh gateway`、`./deploy.sh workstation`，参数见 AI-INSTALL.md。不要在 Docker Desktop 上选择这些 macvlan 入口。

后续操作固定使用本次选择的 Compose 文件，例如：

```sh
docker compose --env-file .env -f compose.portable.yaml ps
docker compose --env-file .env -f compose.portable.yaml restart
```

## Linux 原生安装

先检查 `/etc/os-release`、用户空间 CPU、现有进程、用户、端口和数据。安装器预览不会修改系统，`--apply` 才安装依赖与专用服务。安装会添加系统软件包、独立 `dev` 账户（UID/GID 1100）、`/usr/local/bin` 工具和 systemd 服务；需要空闲的对应路径和端口。

```sh
cp native/native.env.example /安全的私有路径/ai-workstation-native.env
chmod 600 /安全的私有路径/ai-workstation-native.env
# 预览；也可 --role gateway 或 --role workstation
python3 install-native.py --role all
# 对已确认的新环境执行
sudo python3 install-native.py --role all \
  --config /安全的私有路径/ai-workstation-native.env --apply
```

原生网关：`/opt/gateway`、`/var/lib/ai-gateway`、`ai-gateway.service`；网页 8080、SSH 2223、代理 7890、AdGuard DNS 1053。原生工作站：`/opt/workstation`、`/etc/workstation`、`/home/dev`、`ai-workstation.service`；SSH 2222、VNC 5901、网页桌面 6080。私有初始化文件为 `/etc/ai-workstation-native.env`，权限 600。两个角色可装在同机，也可装在不同 Linux 主机上；分别设置访问端点和实际代理。

**原生安装保留宿主已有 root 密码、主 SSH 配置、Nginx 配置及系统地区。** 网关管理用户名默认为 `root`，原生网关 SSH 使用宿主现有 root 密码（若宿主锁定 root，则保持锁定）；工作站专用 SSH 只开放 `dev`，默认 `dev / root`。宿主 root 管理继续通过原有 SSH 入口。原生安装不会把现有 Linux 服务器的 root 密码重置为 `root`。应用地区只应用于专用工作站用户和进程。

原生服务默认也只监听 `127.0.0.1`，通过宿主现有 SSH 隧道访问。需要 LAN 访问时明确修改专用服务的绑定参数、专用 SSH 配置及宿主防火墙。原生入口默认作为应用服务运行，使用 userspace Tailscale，保留宿主路由和 DNS。需要接管 LAN 时须先规划 TUN、转发、防火墙和 DNS 监听冲突，再显式配置透明网关；不因安装而自动改动现有网络。安装器遇到已有用户、数据、工具、Tailscale 或占用端口时停止，不清理冲突对象。软件包安装期间暂时抑制自动启动其他服务，随后恢复原有策略。

```sh
systemctl status ai-gateway ai-workstation
journalctl -u ai-gateway -u ai-workstation --since today
sudo systemctl restart ai-gateway ai-workstation
```

先验证网页登录、DNS 真实查询、代理真实请求、SSH 身份与权限、桌面画面和应用启动，再验证服务重启后数据与 SSH 指纹保留。CI 在可丢弃的 Linux 环境中验证原生安装、独立服务配置和运行流程；systemd 开机启动、不同宿主防火墙及具体设备仍需在安装现场验收。

## 从源码构建其他架构

不强制 `platform: linux/amd64`，Docker 按 Engine 的 CPU 选择镜像。使用交叉构建时显式选平台，并先为网关准备相同架构的 seed：

```sh
python3 gateway/scripts/fetch-components.py arm64
docker buildx build --platform linux/arm64 --load -t gateway-local:test gateway
# ARMv7 对应 fetch 参数 armv7、Docker 平台 linux/arm/v7
# RISC-V 对应 riscv64、linux/riscv64

docker buildx build --platform linux/arm64 --load -t workstation-local:test workstation
```

网关 Dockerfile 检查 seed 架构是否匹配，防止拿旧 amd64 文件打包为 ARM 镜像。为其他 CPU 构建时，选用提供其 Linux 用户空间、APT 和所需包的 `BASE_IMAGE`；工作站通过 `WORKSTATION_BASE` 配置基础镜像。离线基础镜像下载脚本支持 `--platform linux/arm64` 等参数。跨架构执行可能需要 QEMU；模拟运行通过后仍应报告是否做过对应硬件验收。
