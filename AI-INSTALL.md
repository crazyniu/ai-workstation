# 给 AI 的容器安装与升级指南

从 [README 的四条指令](README.md#让-ai-安装或升级容器) 选择本次操作。每条只授权安装或升级一个角色，250 和 251 都是容器的局域网地址。

| 目标 | GitHub 发布镜像 | 首次安装入口 |
| --- | --- | --- |
| 250 网关 · `192.168.1.250` | `ghcr.io/crazyniu/ai-workstation-gateway:latest` | `./deploy.sh ai gateway` |
| 251 工作站 · `192.168.1.251` | `ghcr.io/crazyniu/ai-workstation:latest` | `./deploy.sh ai workstation` |

只使用表中对应的项目镜像和仓库自带的 Compose 配置。软件随镜像交付，禁止自行选型、另外装包、本地构建替代镜像或改用宿主机原生安装。镜像无法拉取、地址冲突、宿主缺少必要工具或 251 无法使用现有 250 网关时，报告具体阻塞。安装前发现已有目标容器时停止；升级找不到原容器时也停止。

新容器的管理员为 `root/root`，网关网页密码为 `root`。工作站桌面用户为 `dev/dev`，VNC 密码为 `root`。升级保留用户已有的配置和身份。

## 首次安装先确认国家

部署所选角色前，先向用户询问国家并等待答复。使用用户已确认的选项时，例如美国，执行 `AI_INSTALL_COUNTRY=US ./deploy.sh ai workstation`；PowerShell 中先设置 `$env:AI_INSTALL_COUNTRY='US'`。交互式安装可直接在终端选择。非交互安装缺少确认时会停止。升级沿用已有地区设置。

| 国家 | 系统语言 | 时区 |
| --- | --- | --- |
| 新加坡 SG | 英语 | Asia/Singapore |
| 台湾 TW | 繁体中文 | Asia/Taipei |
| 美国 US | 英语 | America/Los_Angeles |

其他国家另行确认语言代码和 IANA 时区，分别通过 `AI_INSTALL_LANGUAGE` 和 `AI_INSTALL_TIMEZONE` 传入。地区只应用于本次选择的容器；代理出口由网络设置决定。

## 0. 先确定角色、宿主机和网络拓扑

`250` 指网关角色，`251` 指工作站角色，不代表宿主机地址，也不要求这两个角色位于同一设备。首次部署先记录下表，再连接对应 Docker context；外部环境可能是 **工作站 251 在宿主机 A、网关 250 在宿主机 B**。宿主机地址、网卡名、磁盘及容器名按现场填写。

| 项目 | 宿主机 A：工作站 | 宿主机 B：网关 |
| --- | --- | --- |
| 需要现场核实 | SSH 地址、Docker context、LAN 接口、子网、数据盘、已有容器 | SSH 地址、Docker context、LAN 接口、子网、数据盘、已有容器 |
| 容器角色 | workstation，默认 `192.168.1.251` | gateway，默认 `192.168.1.250` |
| 私有配置 | A 自己的 `.env`、密码和镜像版本 | B 自己的 `.env`、密码和镜像版本 |

在所选角色的 Linux Docker 宿主机上使用表中入口。同机也可分别安装；每个入口使用独立的 Compose 项目。工作站的默认路由和 DNS 指向现有的 250。已有部署升级时沿用其实际的容器定义、网络和地址，流程见第 5 节。

## 1. 确认目标，先只读盘点

LAN 部署环境为 **Linux Docker Engine 与对应 CPU 镜像**，要求 **Docker Compose 2.33.1 或更新版本**、macvlan 及可用的物理 LAN 接口；网关还需要 `/dev/net/tun`。macOS / Windows 控制端可通过 SSH 操作目标 Linux 宿主机。仅在本次所选角色的宿主机盘点。

先查看以下信息，暂不创建、停止、删除或重建容器：

```sh
uname -srm
docker context show
docker version
docker compose version
docker info --format 'Architecture={{.Architecture}} DockerRootDir={{.DockerRootDir}}'
ip -brief address
ip route
docker ps -a --format 'table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Image}}'
docker network ls
docker volume ls
ls -l /dev/net/tun
```

进一步核对：

- **网卡与网段**：实际接入 LAN 的接口可能是 `eth0`、`enp…`、桥接接口或 NAS 的虚拟交换接口。根据地址、默认路由及宿主网络配置确定，不直接套用示例。确认系统支持所需 macvlan 和网络权限。
- **DHCP 与地址**：对需要 macvlan 地址的 LAN，读取相应路由器的 DHCP 地址池、保留地址与租约，检查候选地址的 ARP / 邻居记录；必要时从同一 LAN 做有限的冲突探测。没有 ping 回复不证明地址空闲。同一 LAN 模式的两角色地址应在该 LAN 内、未被占用，并从动态分配范围排除；跨网段时分别核对各自所用网段，工作站 bridge 模式无需额外保留一个 251 的 macvlan 地址。
- **已有服务与数据**：盘点所有容器，包括停止的容器。对相关容器只提取名称、ID、Compose 项目标签、状态、挂载目标和网络信息，识别正在使用的配置、HOME、身份及数据位置。避免将完整 `docker inspect`、容器环境变量或私有配置输出到对话。
- **存储与空间**：通过 `DockerRootDir`、`findmnt` / `df` / `lsblk`（以宿主可用工具为准）查明 Docker 实际存储所在磁盘、剩余空间及 SSD 情况，不只根据目录名判断。镜像、容器写入层及构建缓存均可能占用空间。

发现任何已有容器时，**先暂停首次创建流程并评估原服务**。不要直接执行 `deploy.sh`、`compose up --force-recreate`、`compose down` 或清理命令。若目标项目已存在，按“已有环境”处理；如果只是宿主其他项目，也须先确认新增环境不会冲突，并保留那些容器和数据。不要根据 IP 的旧用途决定删除对象。

如果缺少当前拓扑需要的目标主机、LAN 接口、空闲地址、DHCP 信息或密码设置方式，只询问无法通过授权的只读检查确定的信息。用户未要求变更的全局网络、路由器 DHCP、现有代理和系统软件不随安装调整。

## 2. 确定配置与数据约定

| 项目 | 默认值或要求 |
| --- | --- |
| 网关 | `192.168.1.250`，Clash / Mihomo、DNS、Web 后台、Tailscale |
| 工作站 | `192.168.1.251`，Claude / Codex、XFCE、SSH / VNC |
| 上游路由器 | 示例为 `192.168.1.1`，以现场路由为准 |
| control bridge | 示例为 `172.30.100.0/24`，必须避开 LAN、现有 Docker 与 VPN 路由 |
| NAS / 宿主访问 | 需要时填写 `HOST_ADDRESS`，随后验证实际访问路径 |
| 业务数据 | 各自容器内部；不增加宿主目录绑定、命名数据卷或隐式匿名业务卷 |
| 工作站 HOME | `/home/dev`；配置、项目、登录身份及 SSH 主机密钥留在容器内部 |
| 工作站国家 / 语言 / 时区 | `WORKSTATION_COUNTRY=SG`、`WORKSTATION_LANGUAGE=en`、`WORKSTATION_TIMEZONE=Asia/Singapore`；初始化为新加坡英文 `en_SG.UTF-8` |

首次安装时确认目标地址属于现场 LAN 且空闲；有冲突时报告并停止。按实际网卡填写 `LAN_INTERFACE`，保留目标角色的 Compose 网络、设备及安全设置。

Docker 的 `data-root` 属于宿主存储设置。**默认不迁移 Docker 数据目录、不改宿主网络、不向公网开放端口。** 如果 SSD 尚未用于 Docker，先报告实际位置、空间及影响；只有用户明确授权后，才另行安排涉及所有受影响容器的存储迁移和回退。容器内部保存业务数据，不代表这些字节脱离宿主 Docker 存储。

### 工作站网络权限与出口验收

需要把某个工作站的境内外公网流量和 DNS 都固定到同一个现有代理节点时，使用[独立出口与 DNS 配置流程](docs/workstation-egress.md)。该流程仅处理指定来源的规则和 AdGuard 客户端，保留其他设备的 DNS 和分流；必须先满足 LAN 透明网关和直连保护前提。

默认 Linux LAN 安装由 `workstation` 直接持有 251 地址，允许 251 主动连接 Mac 的 Orca 服务。仅在用户明确选择 `--isolate-lan` 时，工作站角色包含 `workstation` 和 `workstation-network` 两个服务，使用同一工作站镜像。后者持有 251 地址及 NET_ADMIN，先装载 nftables 规则。前者共享该网络命名空间，移除 NET_ADMIN 和 NET_RAW，启动 SSH 和桌面前等待本命名空间的隔离规则就绪。核对地址时查看辅助容器。部署不添加业务卷、Docker socket 或宿主防火墙规则。

隔离模式下，251 可回复来自管理端的 SSH、VNC 和网页桌面连接，可向 250 查询 DNS 或使用代理。主动连接内网、链路本地、组播等目标会被阻止。250 同时限制 251 通过网关代理访问本地目标。两台宿主分别部署时，两端都需要支持隔离的镜像与 Compose；升级一个角色并不能更新对端。可从普通 LAN 客户端和 251 分别验收，以区分入站管理与工作站主动访问。

固定软件或来源的出口应选具体代理节点。验收时区分匹配到的规则、代理组当前选择和实际节点。只在用户指定的维护窗口测试节点失效和 UDP 拒绝，正常运行时保留其他设备的连接。portable、独立 bridge 和原生安装的网络权限见[平台说明](docs/platforms.md)。

以上能力由新建容器的安全配置决定；已有容器只执行 `restart` 不会更新能力集合。按已有环境流程保存内部数据并验证恢复，再应用新的容器配置；不要对有数据的部署直接运行 `compose up --force-recreate`。

### 网页桌面

noVNC 入口为 `https://工作站地址:6080/`，与 5901 的 VNC 共用桌面；bridge 部署通过到宿主的隧道访问回环映射端口。默认要求 VNC 密码；只有用户明确要求可信私网免密码时才配置 `VNC_AUTH=none`，并说明此配置同时关闭原生 VNC 密码。保留 SSH 的独立认证，不新增公网端口映射。

可信内网需要免证书提示时，显式设置 `NOVNC_TLS=0`，改用 `http://工作站地址:6080/`；配合 `VNC_AUTH=none` 即为免密码 HTTP 桌面。此连接不加密，文字通过 noVNC 左侧剪贴板面板传递；依赖安全上下文的浏览器 API 会受限。默认仍为 `NOVNC_TLS=1` 的 HTTPS。自定义 `NOVNC_ALLOWED_ORIGINS` 必须与实际入口的协议和端口一致。

HTTPS 模式首次启动生成容器内部的自签名证书，浏览器首次访问需要确认；HTTP 模式不生成或使用证书。使用自定义域名或不同外部端口时，把实际来源填写到 `NOVNC_ALLOWED_ORIGINS`；内置 WebSocket 来源校验不会接受任意网站发起的连接。按选定协议验收页面、真实 WebSocket/VNC 握手、浏览器画面、中文和多行文字双向剪贴板、重启后身份与桌面。公共镜像不得包含生成的 TLS 私钥。

### 2.1 工作站国家、语言和时区初始化

这些参数仅控制 **251 容器内部** 的地区格式、界面语言和时区；宿主机地区与公网出口由各自配置决定。国家使用大写两位 ISO 代码，语言使用小写两位或三位 glibc 语言代码；初始化将两者组合成 `语言_国家.UTF-8` 并按需生成 locale，时区使用有效 IANA 名称。国家与时区并非一一对应，修改地区时明确填写全部三项。

```dotenv
# 默认：新加坡、英文
WORKSTATION_COUNTRY=SG
WORKSTATION_LANGUAGE=en
WORKSTATION_TIMEZONE=Asia/Singapore

# 例如台湾繁体中文：TW / zh / Asia/Taipei
# 例如美国英文（洛杉矶）：US / en / America/Los_Angeles
```

通常使用镜像中 `/usr/share/i18n/locales` 支持的语言/国家组合。台湾英语 `TW / en / Asia/Taipei` 使用明确的组合：`en_US.UTF-8` 提供英语界面，`zh_TW.UTF-8` 提供台湾日期、货币、地址等地区格式；`LC_ALL` 留空以允许分类设置，`LANGUAGE=en_US:en` 和 `LC_MESSAGES=en_US.UTF-8` 保持英语消息。glibc 没有 `en_TW`，不生成虚构的 locale。其他无效代码、缺失的 locale 或时区会让初始化明确失败。以 `WORKSTATION_*` 三项为输入，初始化统一设置语言、地区分类、`TZ`、`/etc/default/locale`、PAM 环境、登录 Shell 和桌面会话；不要另设互相矛盾的 `LANG` / `TZ`。此行为要求镜像已包含对应版本的 `/etc/workstation/region.py`；核对所选镜像的构建/发布版本，不把当前源码改动说成已有 `latest` 镜像功能。

**已有容器修改地区：** 仅改 `.env` 后执行 `docker compose restart` 不会更新容器定义中的环境变量。对已经包含新初始化程序的容器，可写入它内部的 `/etc/workstation/region.json`，其中提供的字段优先于运行时环境变量，未提供的字段沿用环境变量和默认值。该文件无需业务挂载，重启保留。先确认实际容器使用此初始化入口；现有旧镜像或其他 HOME 布局不能直接套用。以下在 **A 的实际部署目录** 执行，并替换 Compose 文件名：

```sh
workstation_compose=compose.workstation.yaml  # 同机用 compose.yaml；bridge 用 workstation/compose.yaml
docker compose --env-file .env -f "$workstation_compose" exec -T --user 0 workstation python3 - <<'PY'
import json
from pathlib import Path
path = Path('/etc/workstation/region.json')
path.write_text(json.dumps({'country': 'SG', 'language': 'en', 'timezone': 'Asia/Singapore'}) + '\n')
path.chmod(0o600)
PY
docker compose --env-file .env -f "$workstation_compose" restart workstation
docker compose --env-file .env -f "$workstation_compose" exec -T workstation \
  runuser -l dev -c 'locale; cat /etc/timezone; date'
```

地区配置在入口启动时生效，现有 SSH/桌面会话应重新连接后验收。直接 `docker exec ... locale` 可能仍显示容器创建时的 ENV，应检查实际登录用户和 XFCE 进程的环境；不要据此重建容器。删除内部 `region.json` 后，在下次正常重启时恢复使用容器运行时参数。

### 2.2 手动重置 Claude Code 用户信息

日常清缓存使用菜单 **6**，先看路径与大小，再由用户确认。它独立于下方的账号重置，安装和升级时均不自动执行。

新镜像包含 `/usr/local/bin/niu.sh`，源码为 `workstation/desktop/niu.sh`。此命令供用户主动更换账号或清理本地身份时使用，安装、启动、重启和升级都不自动调用它；不因安装验收而删除用户的真实身份。

在 251 以 `dev` 打开桌面的 **niu.sh**。输入 **5** 查看清理清单，关闭 Claude Code 后输入 **1** 确认，或输入 **0** 取消。安装或更新时不要自动选择此项。

- 清理本地 Code OAuth 登录字段、用户与设备标识、账号缓存、会话/输入历史、调试/遥测/用量、会话文件与已存在的 Claude 配置备份；不生成新的身份恢复副本。
- 在 `.claude.json` 中保留 MCP 配置，在 `.credentials.json` 中保留 `mcpOAuth` 和插件凭据；插件、技能、通用代理与真实项目目录保持。项目设置中的 MCP 项保留，项目会话/用量项清理。
- 在 Claude settings 和用户 Shell 启动文件中，仅清理明确的 Code 认证变量及 `apiKeyHelper`。复杂的 Shell 认证赋值会中止计划，需先人工核对；不执行 Shell 配置，不输出凭据值。
- 默认处理当前用户 HOME 的 `.claude`。使用 `CLAUDE_CONFIG_DIR` 时，该值必须是 HOME 内独立的绝对配置目录；拒绝 HOME 本身、父路径穿越及符号链接目标。
- 应用前检查目标用户的 Claude 进程和继承的认证环境变量。继承的认证变量需要在其实际来源中处理并重新打开干净会话；不要以反复执行清理代替检查容器的认证配置。清理中 Claude 再次启动时会停止并报告已完成部分。
- 范围是本机当前 HOME 的 Claude Code 文件；浏览器资料、服务器端会话、共享 Shell 历史和其他用户目录独立处理。不得将本地文件清理说成服务端注销或所有外部身份均已删除。

规则参考 [CCBaga 固定提交的配置清理实现](https://github.com/liseami/CCBaga/blob/bdfb90ceadfc5fae6772ffff597bddecb0b73cc3/src-tauri/src/cleaner_config.rs)，适配 Linux 并保留 MIT 声明。使用临时 HOME 验证清理、预览和 MCP 保留；对真实部署只做用户已要求的操作。旧镜像若未安装命令，先确认镜像版本和迁移方案，保留原数据。

## 3. 准备私有配置，执行首次部署

仅在确认属于首次部署、没有冲突及需要保留的目标容器后执行。使用干净的仓库副本；已有目录先检查用途，不覆盖其中的 `.env` 或未提交文件。

```sh
git clone https://github.com/crazyniu/ai-workstation.git
cd ai-workstation
cp .env.example .env
chmod 600 .env
```

按实际网络填写私有 `.env`，保留表中的镜像、IP 和初始账号设置。网关使用 `GATEWAY_USER=root`、`GATEWAY_PASSWORD=root`、`WEB_PASSWORD=root`；工作站使用 `WORKSTATION_ROOT_PASSWORD=root`、`WORKSTATION_PASSWORD=dev`、`VNC_PASSWORD=root`、`VNC_AUTH=password`。不要在日志中输出私有配置。

执行表中所选角色的首次安装命令。入口在拉取前核对角色、镜像和地址，并拒绝覆盖已有的 Compose 容器。记录实际拉取的镜像摘要。

## 4. 在实际环境验收

以下供用户按所选角色验收。macvlan 的宿主访问限制不等于 LAN 服务故障；先区分访问来源，再检查 control bridge 或宿主防火墙。只执行当前部署需要的检查，复用仍有效的结果。

| 检查 | 必须确认的实际结果 |
| --- | --- |
| 容器、镜像与网络 | 核对目标角色的容器 ID、镜像摘要、LAN 地址和状态；默认在 `workstation` 上核对 251 地址，显式隔离模式则在 `workstation-network` 上核对。 |
| 内部数据 | 在各自宿主机检查实际容器的 `Mounts` 与镜像 `Config.Volumes`，确认没有外置业务挂载或匿名业务卷。设备映射按所选 Compose 单独核对。 |
| 网关 Web | 实际打开主页并登录，检查控制面板及服务入口；`/healthz` 成功只说明健康接口可用。 |
| DNS | 普通 LAN 客户端明确向网关查询 `home.arpa`，结果为本次网关 IP；再查询外部域名。确认需要使用本地域名的客户端实际采用该 DNS，而不是被加密 DNS 绕过。 |
| 代理与出口 | 用户导入配置并选择节点后，从工作站或测试客户端经实际代理发起 HTTPS 请求，检查成功响应和所用出口；按需要核对直连 / 代理分流。干净镜像默认直连，不能据此宣称个人代理已就绪。 |
| SSH 与桌面 | 使用工作站普通用户 `dev` 实际登录 SSH；用 VNC 客户端连接桌面，确认画面、输入和终端可用。启动 Claude / Codex 的真实桌面入口，确认没有立即退出或连接错误。 |
| 工作站地区与语言 | 普通用户登录后检查 `locale`、`/etc/timezone` 和 `date`，核对 XFCE 会话与桌面菜单语言。默认应为 `en_SG.UTF-8` / `en_SG:en` / `Asia/Singapore`。重启同一容器后再次确认自定义值生效，HOME、MCP 与登录身份保持。 |
| Tailscale | 用户授权后检查账号连接、子网批准状态，并从另一台已授权设备实际验证所需方向的访问；本机状态显示 connected 不替代 peer 测试。 |
| NAS / 宿主 | 配置了 `HOST_ADDRESS` 时，从业务实际访问方测试需要的 NAS 页面或服务，核对路径。没有此需求则标为不适用。 |
| 重启 | 在新部署验收窗口重启同一容器，复查服务、数据、配置、身份和路由；已有服务按用户授权安排。另查各宿主机 Docker 与数据盘启动依赖；经授权重启 A/B 后分别验收，不把一台机器的通过结果当成另一台的结果。不要用重建测试持久性。 |

下面是同机 LAN 部署的基础状态与 DNS 检查示例，地址须替换为实际值；分开部署时带上实际 Compose 文件，并从 A 检查 B 的可达端点。bridge 模式按实际 DNS/代理设计测试。这些检查不能代替上表的完整交互验证：

```sh
docker compose ps --all
curl --noproxy '*' --fail http://192.168.1.250/healthz
nslookup home.arpa 192.168.1.250
nslookup example.com 192.168.1.250
```

日志可能含订阅地址或其他私有信息，只读取定位所需片段并脱敏。不要回显登录令牌、代理认证或完整配置。公开站点根页的 `403` / `404` 最多说明部分连接路径可达，不能证明登录或模型请求成功。

个人服务尚未登录时明确记录 **需用户登录**；无法执行的实际访问标为 **NOT RUN** 并说明缺少的客户端或账号；发现失败记录原因与下一步。容器 healthy、单元测试、镜像构建成功均不能单独作为“安装全部正常”的结论。

### 4.1 Mac Orca 远程执行验收

用户选择 Mac Orca 控制、Linux 工作站执行时，按 [Orca 远程执行说明](docs/orca-remote.md) 检查现有 dev 用户、实际 HOME、SSH、managed server 和配套 CLI。Orca 部署须另行指定。将 Mac 操作、远程账号授权、项目文件读写、智能体真实调用及重启恢复分别记录；个人部署结果和日志留在私有验收目录。

## 5. 已有环境、升级与数据恢复

**重启同一个容器保留内部数据；删除、`compose down`、强制重建或替换容器会失去原容器可写层。** `docker compose restart` 不会把新的镜像或已修改的 Compose 环境变量应用到已有容器。

1. 在目标 Docker 宿主机上核对容器 ID、地址、网络、挂载及启动定义。Compose 部署沿用原项目名、文件和私有环境配置；手工创建的旧容器按其实际定义制定迁移方案。目标不明确时停止。
2. 先拉取表中目标角色的官方镜像，记录摘要。现有容器已运行同一镜像且配置相符时，直接报告已是最新版。
3. 在替换前保存原定义和可回退的私有快照，备份目标角色的数据。250 保留 `/data`、代理订阅、Tailscale 身份、管理账号与 SSH 身份；251 按实际 HOME、UID/GID 备份项目、登录身份、SSH 密钥及内部配置。旧版 HOME 可能是 `/home/developer`。具体命令见[网关升级](gateway/README.md#网关应用状态升级)和[工作站迁移](workstation/README.md#应用状态迁入新的公开镜像)。
4. 只切换目标角色和该版本 Compose 明确声明的同角色配套服务。将备份恢复到新容器后启动，保持目标地址和另一角色的运行状态；切换失败则停止新实例，用旧定义和升级前的数据恢复运行。无可用回退或无法映射原数据时，在替换前停止。

私有备份和运行容器快照含身份及凭据，不进入公开源码、GHCR 镜像或附件。两个使用相同 LAN IP 或 Tailscale 身份的实例不可同时运行。迁移与清理范围超出用户已授权的首次安装时，先说明具体影响，再取得相应授权。

## 6. 最终交付给用户

用简短结果报告和验收清单交付：

- **实际入口**：网关 Web / DNS 地址、工作站 SSH / VNC 地址、账号名及密码的私有保存方式；报告不包含密码。
- **部署身份**：使用的仓库提交、镜像标签和摘要、目标角色的宿主机和实际启动定义、容器名称 / ID / 状态，以及各宿主容器总数；解释保留的其他项目。
- **数据位置**：确认业务数据在各自容器内部、实际挂载检查结果、宿主 Docker 存储位置及是否 SSD；说明本次是否改过宿主设置。
- **验证结果**：逐项列出 PASS、FAIL、NOT RUN、需用户登录或不适用，并给出简短实际证据；不将待登录服务或未测模型调用写为 PASS。
- **日常操作**：同容器启停 / 重启方式、内部数据生命周期及上述备份恢复链接；说明后续升级前必须处理数据。
- **剩余事项**：需要用户完成的账号授权、路由批准、客户端设置或未解决问题。仅在全部所需验收通过时报告安装完成；仍有缺口则准确说明已完成范围。
