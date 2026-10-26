# 网关容器

将网关桌面、Mihomo（Clash）、MetaCubeXD 面板、AdGuard Home 和 Tailscale 打包在一个 Ubuntu 24.04 容器中。首页采用可更换壁纸与应用图标，配置、DNS、远程访问、升级和备份集中在设置窗口，支持亮色、暗色和跟随系统。窗口管理基于 [WinBox 0.2.82](https://github.com/nextapps-de/winbox/tree/0.2.82)，静态资源随镜像提供。镜像首次启动不包含代理节点、订阅地址或 Tailscale 登录身份。

## 已安装的软件

| 软件 | 构建版本 / 来源 | 用途 |
| --- | --- | --- |
| Mihomo | `v1.19.33` | Clash 配置、代理转发与网关 DNS |
| MetaCubeXD | `v1.273.1` | 节点选择、测速与代理状态面板 |
| AdGuard Home | `v0.107.79` | DNS 管理、广告过滤与查询记录 |
| AdGuard DNS filter | 锁定的官方规则快照 | 首次启动的基础过滤规则 |
| Tailscale | `1.104.2` | 设备连接与局域网子网路由 |
| 网关桌面 | 本仓库源码 | 配置、账户、桌面链接、主题、升级和备份管理 |
| WinBox / CodeMirror | WinBox `0.2.82`；编辑器版本见随包许可清单 | 桌面窗口与 YAML 编辑 |
| Ubuntu | `24.04` | 基础系统 |
| Python 3 / PyYAML | Ubuntu 系统软件包 | 网关后台、配置处理与健康检查 |
| Nginx / Supervisor / Tini | Ubuntu 系统软件包 | Web 入口、服务管理和容器启动 |
| OpenSSH Server / Git / GitHub CLI | Ubuntu 系统软件包 | SSH 管理、源码与 GitHub 操作 |
| curl / dnsutils / iproute2 / iptables | Ubuntu 系统软件包 | 连通性检查、DNS 查询、路由和防火墙 |

组件的精确下载地址及 SHA256 见 [`components.lock.json`](components.lock.json)，编辑器依赖见 [`web/assets/editor-licenses.txt`](web/assets/editor-licenses.txt)，安装定义见 [`Dockerfile`](Dockerfile)。APT 软件版本由构建时的软件源决定。开发用 Python、AI CLI 和 MCP 工具位于 [工作站容器](../workstation/README.md)。

## 部署前准备

网关不限定 NAS 或 CPU。Linux、Windows、macOS 的通用 Docker 入口为仓库根目录 `./deploy.sh gateway-portable` / `.\deploy.ps1 -Role gateway-portable`；Linux 可选原生安装。架构、默认 root/root 管理账号、端口和网络边界见[平台安装说明](../docs/platforms.md)。以下本目录 Compose 为 Linux LAN macvlan 专用，需要 Compose 2.33.1+、TUN、iptables 和真实 LAN 接口。

下列命令用于在本目录首次创建独立网关。双容器部署从仓库根目录使用 `./deploy.sh all`；该脚本发现已有容器（包括停止的容器）会退出。已有环境使用 `docker compose start` / `restart`，更换镜像前先按下文备份恢复。

选择局域网内未占用、在 DHCP 分配范围以外的固定地址。配置网段应与物理 LAN 一致；使用独立测试地址验证后再切换原网关地址。以下示例 `192.168.10.2` 是文档地址，请替换为实际网络。

```sh
cp .env.example .env
# 编辑 .env 中的 LAN 地址、上游路由器与物理接口
chmod 600 .env
docker compose config --quiet
docker compose up -d --no-build
docker compose ps
```

首次从源码构建时，先下载锁定版本，再构建本地镜像：

```sh
python3 scripts/fetch-components.py amd64
docker compose build --pull
docker compose up -d --no-build
```

若宿主配置的镜像加速源不可用，可仅对此次构建设置 `GATEWAY_BASE_IMAGE=public.ecr.aws/ubuntu/ubuntu:24.04`，使用 [Canonical 官方 ECR 发布](https://ubuntu.com/docs/oci-registries/oci-how-to/getting-started/)，无需修改宿主的全局镜像源。

下载器从官方来源校验 SHA256，版本与下载来源记录在 `components.lock.json`。Python 下载工具只使用标准库；需安装 `curl`。不带 `--refresh` 时使用锁定版本，同版本同架构的 `seed/` 复用，切换架构时验证下载后替换旧文件。要更新构建用默认组件，应在干净工作副本重新下载并审核新 lock，运行中的服务升级使用设置页。

`.env` 中的主要参数：

| 参数 | 用途 |
| --- | --- |
| `GATEWAY_LAN_ADDRESS` | 网关固定 IPv4/CIDR，例如 `192.168.10.2/24` |
| `GATEWAY_LAN_ROUTER` | 原有主路由器地址，例如 `192.168.10.1` |
| `GATEWAY_PARENT_INTERFACE` | 宿主物理 LAN 接口，例如 `eth0` 或 NAS 的实际接口名 |
| `GATEWAY_HOST_ADDRESS` | 可选，NAS 宿主的 LAN IPv4；经 control bridge 访问它 |
| `GATEWAY_CONTROL_SUBNET` | control bridge 网段，必须避开 LAN、现有 Docker、Tailscale/VPN 路由 |
| `GATEWAY_BRIDGE_ROUTER` | control bridge 网关，必须位于 control subnet 内 |
| `GATEWAY_CONTROL_ADDRESS` | 容器 control bridge 地址，与上述 bridge 网关处于同一网段 |
| `GATEWAY_IMAGE` | 本地镜像标签，默认 `gateway-local:1.0.0` |
| `GATEWAY_BASE_IMAGE` | 构建用 Ubuntu 官方镜像，默认 `ubuntu:24.04` |
| `GATEWAY_ADMIN_PASSWORD` | 全新容器初始网页密码，默认 `root`；已有密码不覆盖 |
| `GATEWAY_CONTAINER_USER` / `GATEWAY_CONTAINER_PASSWORD` | 容器 SSH 账号和密码，默认 `root` / `root`；启动时应用 |

macvlan 使容器拥有独立 LAN 地址，因此不映射宿主的 80/53 端口。uplink 设置 `enable_ipv4: false`，关闭 Docker 自动 IPv4 地址分配，启动脚本在容器内设置固定 LAN 地址及上游默认路由。宿主与 macvlan 容器默认不能直接通信；control bridge 和可选宿主 `/32` 路由解决容器到 NAS 的访问。宿主可经 control 地址打开主页，LAN 用户使用 LAN 地址。宿主防火墙仍须允许需要的 bridge 流量。

## 首次设置与日常使用

1. 用局域网浏览器打开 `http://192.168.10.2`，默认管理员密码为 `root`。登录后可在“设置 → 账户”修改，支持 1–256 个字符。`GATEWAY_ADMIN_PASSWORD` 只用于全新容器首次初始化；重启保留已保存的网页密码。删除或重建容器前应备份，并在新容器启动前恢复数据。改密后当前浏览器会话续期，其余旧会话失效。

   容器 SSH 默认账号和密码均为 `root`，可通过 Compose 的 `GATEWAY_CONTAINER_USER` 和 `GATEWAY_CONTAINER_PASSWORD` 修改，重建后应用；SSH 账号设置与网页密码独立。新建容器的 root HOME 位于 `/data/home`，随 `/data` 备份；Linux 原生安装保留宿主 root HOME。GitHub CLI 已安装，使用自己的账号运行 `gh auth login`，凭据保存在容器内部 HOME 中，干净镜像不包含个人登录。

   可信私网可在“设置 → 账户 → 密码登录”关闭“进入网关时需要密码”，输入当前密码并保存。关闭后，能访问网页的设备可直接管理网关、Clash 和 AdGuard Home；SSH 认证独立保留。原网页密码和登录开关保存在容器内部，重启沿用，改密不会改变开关。重新开启仍需当前密码，并使其他旧会话失效。全新容器默认开启密码登录；管理员密码和登录开关均不随配置备份导出或恢复。
2. 进入“设置 → 代理配置”，点击“上传配置文件”，选择已有的 Clash/Mihomo `.yaml` 或 `.yml` 文件（最大 2 MB）。文件载入后可在编辑器查看和修改，点击“保存并应用”才会生效；校验失败会保留原配置。相同配置重复保存会确认当前服务状态并直接完成；修改规则时复用未变化的节点订阅缓存，只刷新新增、修改或缺少缓存的订阅。高级订阅的手动刷新和定时更新仍会刷新全部节点订阅，失败时回滚。首次导入或修改订阅来源仍需要等待实际下载。成功应用后再调整客户端网关。初始配置采用直连，不提供个人代理节点。
3. Clash 图标打开内置节点面板；AdGuard Home 图标打开广告过滤与 DNS 管理。使用主页管理员会话进入这些服务。
4. Tailscale 在设置中点击“登录并连接”，打开授权页面登录自己的账号。网关根据现有 LAN 地址和前缀自动识别、发布内网子网，同时接收其他设备发布的子网路由，用户无需填写网段或保存路由。已有登录身份也会在后台自动应用此配置；网关 DNS 保持原设置。页面每 4 秒自动更新连接和路由状态，后台每 30 秒校验配置并重试失败项。
   - 页面按状态只显示“登录并连接”“打开授权页面”“连接”或“断开连接”中的一项；“账号操作”中可退出账号。断开连接保留身份，后台不会自动重连。
   - 内网路由生效仍取决于账号侧批准与访问策略。配置了 [Tailscale autoApprovers](https://tailscale.com/docs/features/subnet-routers) 的账号可自动批准；其他账号会显示待批准状态和管理控制台入口。`PrimaryRoutes` 确认本机成为该子网的主路由后显示“子网路由已生效”；该状态不代替远端设备实际连通性验收。远端 Linux 客户端需启用接收子网路由。
   - 自动识别优先使用 `GATEWAY_LAN_ADDRESS` 的实际前缀；未设置时仅检查运行时选定的 LAN 接口，避开 Docker/VPN 接口及 Tailscale 地址。自动配置会替换旧手动发布的非默认网段，保留账号身份及其他服务配置。
5. 添加自己的应用链接：填写名称和 HTTP/HTTPS 地址，默认自动获取网站图标，也可手动选择内置图标；支持其他 LAN IP 和端口；可以编辑、删除和调整顺序。

镜像包含 [AdGuard DNS filter 官方规则](https://github.com/AdguardTeam/AdGuardSDNSFilter)的锁定快照，全新容器首次启动即可加载这份基础过滤规则，无需先联网下载。规则快照随构建版本记录，默认由 AdGuard Home 每 24 小时从官方地址检查更新；可以在 AdGuard Home 原生界面管理过滤列表。离线时继续使用已保存的规则。重启同一容器保留自身规则与配置；重建时需先恢复私有备份，初始化不会覆盖已恢复的规则。

上传的 YAML 文件就是日常配置入口。只有需要链接订阅时，才展开代理配置页下方的“高级：订阅链接”，填写直接返回 Clash/Mihomo YAML 的 HTTP/HTTPS 地址，可手动刷新或设置定时更新。导入不会接入第三方订阅转换服务。

代理配置中的节点、规则和提供者来自用户，导入时保留网关必需的监听、控制认证和 DNS 参数。管理界面提供 HTTP LAN 入口，远程管理建议经 Tailscale 访问；公网反向代理应由部署者提供 HTTPS。

## 桌面与设置窗口

- 默认入口为 Clash、AdGuard Home、Tailscale、工作站和设置。Clash 与 AdGuard Home 的链接跟随当前网关访问地址生成；工作站默认打开 `https://192.168.1.251:6080/`，可在“设置 → 桌面管理”或右键工作站图标的“设置入口地址”中修改 IP、域名、协议和端口。
- 在桌面空白处右键，可添加链接、刷新桌面、按名称排列全部图标、打开个性化设置或控制面板。在自定义图标上右键，可打开、编辑或删除链接；内置入口保留。
- 内置图标和自定义链接均支持拖动排序，聚焦图标后可按 `Alt + ↑ / ↓` 调整；“设置 → 桌面管理”中的上移、下移按钮用于自定义链接。工作站地址与桌面顺序保存在网关内部，刷新、重启及换浏览器后沿用，并包含在网页配置备份中。手机可长按图标打开菜单；键盘可按 `Shift+F10` 打开菜单，方向键选择、`Esc` 关闭。
- 桌面控制面板支持拖动、调整大小、最小化和最大化。顶部“显示桌面”按钮可最小化或恢复设置窗口。手机使用铺满屏幕的设置界面，功能内容独立滚动。
- “个性化设置”可更换 3 MB 以内的 PNG、JPEG 或 WebP 壁纸，选择填充、适应、拉伸、居中或平铺。点击“应用”后保存到容器内部，刷新页面后保留；“恢复默认壁纸”同样需要点击“应用”。
- 保存、导入、账户、链接、个性化及表单校验的反馈统一显示为全局 Toast。桌面显示在右上角，手机显示在顶部；支持关闭，悬停或键盘聚焦时暂停自动收起，提示不会挤动窗口内容。

界面示例：[桌面操作提示](../docs/images/gateway-global-toast-desktop.jpg)、[手机尺寸操作提示](../docs/images/gateway-global-toast-mobile.jpg)。手机尺寸截图来自浏览器响应式视口。

窗口、右键菜单、表单、下拉框和确认弹窗随当前外观模式统一切换。浏览器选择本地文件的系统对话框仍由浏览器提供。

## 使用 home.arpa

默认本地域名为 `home.arpa`，主页入口为 `http://home.arpa`，也可以始终使用 IP 地址。客户端必须实际使用本容器作为 DNS：手动设置 DNS 为网关 LAN 地址，或在主路由器 DHCP 中下发该地址，然后更新客户端 DHCP 租约/DNS 缓存。

浏览器或系统自行设置的加密 DNS 可能绕过局域网 DNS，需要让本地域名查询使用网关。只修改 DNS 不会让全部流量自动经过代理；旁路网关客户端还需按既有接入方式将网关指向容器 LAN 地址。默认不接管主路由器 DHCP。

```sh
nslookup home.arpa 192.168.10.2
curl --noproxy '*' http://192.168.10.2/healthz
```

本地域名在 Mihomo 的 hosts、Fake-IP 排除及 AdGuard 重写中配置，返回部署时的 LAN 地址。域名可在设置中修改。`home.dev` 属于浏览器强制 HTTPS 的域名后缀，当前 HTTP 部署默认使用家庭局域网保留域 `home.arpa`。

## 数据、备份和升级

网关应用状态保存在容器内部 `/data`，包括代理配置、订阅、图标与顺序、壁纸与显示方式、管理员密码散列、会话密钥、Tailscale 设备身份、AdGuard 配置与运行记录、组件历史版本及升级备份。Compose 不设置业务 bind mount 或 volume，Dockerfile 不声明匿名卷。容器可写层存放在宿主 Docker 数据目录；建议宿主将该目录放在 SSD，Compose 不负责迁移宿主存储。

`docker compose restart` 或宿主重启保留同一容器的数据。删除、`down`、强制重建或替换镜像会删除原容器可写层，因此必须先做私有备份，再将数据恢复到新容器后启动。

设置页导出的配置备份包含代理配置/提供者凭据、订阅地址及 Tailscale 身份，是**私密文件**。它不包含全部 AdGuard 查询记录、组件二进制、SSH/GitHub 登录及管理员会话。

### 网关应用状态升级

`/data` 包含网关应用状态；SSH 主机密钥、用户账号和 SSH/GitHub HOME 位于其他目录。以下流程将应用状态迁入新镜像，不代表完整账号与系统迁移。先停止服务并导出 tar 流，避免在宿主目录展开文件时改变数值 UID/GID 或权限：

```sh
set -eu
umask 077
container=$(docker compose ps --all --quiet gateway)
test -n "$container"
private_backup="${HOME}/gateway-private-backups/state-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$private_backup"
docker compose stop gateway
docker cp -a "$container":/data - > "$private_backup/data.tar"
docker inspect "$container" > "$private_backup/container-inspect.json"
tar -tf "$private_backup/data.tar" > /dev/null
(cd "$private_backup" && sha256sum data.tar > data.tar.sha256)
# 仅需备份时可继续使用旧容器：docker compose start gateway
```

确认备份完成后，在 `.env` 中指定并准备好新的镜像。创建新容器但暂不启动，将归档直接恢复到同一父目录：

```bash
set -euo pipefail
(cd "$private_backup" && sha256sum -c data.tar.sha256)
docker compose up --no-start --no-deps --force-recreate gateway
new_container=$(docker compose ps --all --quiet gateway)
test -n "$new_container"
docker cp - "$new_container":/ < "$private_backup/data.tar"
# 启动前核对数值属主与权限；保留 tar 归档内的原始值。
docker cp -a "$new_container":/data - | tar --numeric-owner -tvf -
docker compose start gateway
docker compose ps gateway
```

### 完整私有快照与原版本恢复

需要完整恢复 SSH/GitHub HOME、账号库、主机密钥、系统改动和网关状态时，保存停止容器的私有镜像快照，同时保存运行时定义。该方案恢复原软件版本；升级到新公开镜像时应使用明确的数据迁移流程。以下命令在原部署的 Compose 目录执行：

```sh
set -eu
umask 077
container=$(docker compose ps --all --quiet gateway)
test -n "$container"
gateway_stamp=$(date +%Y%m%d-%H%M%S)
private_backup="${HOME}/gateway-private-backups/full-${gateway_stamp}"
private_image="local/gateway-private:${gateway_stamp}"
mkdir -p "$private_backup"
docker compose stop gateway
docker inspect "$container" > "$private_backup/container-inspect.json"
cp .env "$private_backup/runtime.env"
cp compose.yaml "$private_backup/compose.yaml"
docker commit "$container" "$private_image"
docker image save -o "$private_backup/image.tar" "$private_image"
printf '%s\n' "$private_image" > "$private_backup/image-tag.txt"
(cd "$private_backup" && sha256sum image.tar > image.tar.sha256)
docker compose start gateway
```

恢复时使用原项目名及备份中的网络、环境设置；旧实例应停止。设置 `private_backup` 为备份目录，将 `.env` 中的 **`GATEWAY_IMAGE`** 改为 `image-tag.txt` 中的 **`local/gateway-private:时间戳`**，然后执行：

```sh
set -eu
(cd "$private_backup" && sha256sum -c image.tar.sha256)
docker image load -i "$private_backup/image.tar"
docker compose config --quiet
docker compose up --no-start --no-deps --force-recreate gateway
docker compose start gateway
docker compose ps gateway
```

私有镜像保留容器写入层的 UID/GID 和权限，不包含外部挂载或运行中内存；本项目默认 Compose 没有业务挂载。所有快照、环境设置和 inspect 记录仅用于私有恢复，不上传 Git、GHCR 或公开附件。

备份包含个人身份和凭据，应保留权限并离线妥善保存；需完整容器级回退时，还应私下保存旧镜像和容器定义。恢复旧版本时使用升级前的数据备份，避免只回退镜像而保留已改变的数据。私有容器快照或备份不属于公开镜像、GHCR 或离线分发包。

`data/`、实际 `.env` 和备份仅供本地运行与恢复，不得加入 Dockerfile 复制项、构建允许清单或 `seed/`。`.dockerignore` 使用允许清单，Dockerfile 只复制程序、静态资源与官方干净组件。已有个人容器的导出结果不作为构建材料。

“设置 → 服务升级”检查 Mihomo、AdGuard Home、Tailscale 和面板的官方稳定版本。下载和 SHA256 校验完成后，先备份受影响状态，逐个切换服务并检查实际控制接口，失败恢复旧程序和配置。升级过程会暂时中断对应代理、DNS 或 Tailscale 连接，应从 LAN 操作。升级程序保存在容器内部 `/data/components`，重启后继续使用；重建或替换镜像前，按上述流程备份并恢复 `/data`。组件无官方校验信息时拒绝升级。离线环境中检查或下载更新不可用，既有服务继续运行。

网关后台、Nginx、Python 和 Ubuntu 通过替换镜像升级。升级前保存旧镜像标签及完整私有数据快照；新镜像启动失败时，停止新容器，使用旧镜像创建容器、恢复升级前数据后启动。仅切换镜像无法撤销数据迁移。不要同时启动两个使用同一 LAN 地址或 Tailscale 身份的容器。

## 离线镜像与迁移

构建后导出可离线加载的干净构建镜像（不包含运行容器的个人数据）：

```sh
scripts/export-image.sh ./dist
```

导出脚本需要 Python 3，会先审计保存的镜像全部层和环境元数据，再生成压缩包与校验文件。发现已知个人数据、凭据或不完整镜像时会中止，清理临时文件并保留已有分发包；不会因为镜像标签看起来像公开版本就跳过检查。不要将私有恢复快照作为分发输入。

离线主机加载并校验：

```sh
cd dist
sha256sum -c gateway-local-1.0.0-amd64.tar.gz.sha256
gunzip -c gateway-local-1.0.0-amd64.tar.gz | docker image load
```

将 Compose、`.env.example` 和此说明带到目标主机，创建自己的 `.env`，执行 `docker compose up -d --no-build`。离线机器不需要 `seed/` 或源码来运行已加载镜像。镜像加载本身不配置网络和客户端网关。

源码包使用独立允许清单导出：

```sh
python3 scripts/export-source.py ./dist
# 可选：同时包含已经校验下载的默认组件，省去再次下载组件
python3 scripts/export-source.py ./dist --include-seed
```

默认源码包包含 Dockerfile、Compose、`.env.example`、程序、网页与资源、启动脚本、锁定版本、许可证、构建/导出脚本和后端测试；存在时也包含 `DESIGN.md` 与 `.impeccable/design.json` 两个设计说明文件。它排除 `data/`、实际 `.env`、个人备份、运行日志、截图、设计审查记录、编辑器缓存和整个工作区的其他目录。默认不包含 `seed/`；带 `--include-seed` 的包只额外纳入 `seed/mihomo`、`seed/adguard`、`seed/tailscale`、`seed/panel`、`seed/filters`，这些目录应始终仅保存官方下载器产物。二者均生成 SHA256 校验文件。

源码包中没有 Ubuntu 基础镜像和 apt 软件包缓存，因此包含 `seed/` 也不表示能够完全离线重新构建。完全离线运行应使用前述 `docker image save` 镜像包。交付前还需审核实际归档内容与镜像各层，允许清单不能代替凭据检查。

迁移已有网关时，应保留旧容器定义、镜像及数据，用全新容器和不冲突的 IP 完成全新启动、网页、DNS、代理、去广告与 Tailscale 验证。私有迁移只复制所需配置/身份到新容器内部 `/data`；保持原始数据完整。验证通过后停止旧容器再接替原地址，失败则停止新容器、恢复旧容器及原始数据。不要从现有个人容器 `docker commit` 生成分发镜像，也不要将私人迁移备份混入离线包。

## 验证边界

`docker compose config` 只验证 Compose 结构，容器 healthy 只表示内置探针通过。正式接替网关前还应在真实客户端验证主页交互、DNS 实际回答、国内直连/代理分流、广告拦截、NAS 访问、Tailscale 双向访问及升级回滚。发行包实际验收状态见随交付的测试记录；未执行项目应明确记录 NOT RUN。

组件来源及许可证见 [NOTICE](NOTICE)，对应版本许可证原文在 `licenses/`，随镜像放在 `/opt/gateway/licenses`。公开镜像由 [GitHub Actions](https://github.com/crazyniu/ai-workstation/actions/workflows/images.yml) 构建并验证，发布来源以提交标签和镜像摘要为准。
