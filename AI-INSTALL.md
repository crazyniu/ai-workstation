# 给 AI 的安装指南

本指南供执行安装的 AI 使用。根据 [仓库地址](https://github.com/crazyniu/ai-workstation) 在用户指定的主机上安装网关和工作站。先读取当前版本的 [README](README.md)、[compose.yaml](compose.yaml)、[.env.example](.env.example) 和 [deploy.sh](deploy.sh)，再按下述流程执行。仓库配置描述预期行为，实际安装结果必须以目标主机和真实客户端验证为准。

## 0. 先确定角色、宿主机和网络拓扑

`250` 指网关角色，`251` 指工作站角色，不代表宿主机地址，也不要求这两个角色位于同一设备。先记录下表，再连接对应 Docker context；外部环境可能是 **工作站 251 在宿主机 A、网关 250 在宿主机 B**。不要把当前家庭环境的宿主机地址、网卡名、磁盘 UUID 或容器名带入新环境。

| 项目 | 宿主机 A：工作站 | 宿主机 B：网关 |
| --- | --- | --- |
| 需要现场核实 | SSH 地址、Docker context、LAN 接口、子网、数据盘、已有容器 | SSH 地址、Docker context、LAN 接口、子网、数据盘、已有容器 |
| 容器角色 | workstation，默认示例 `192.168.1.251` | gateway，默认示例 `192.168.1.250` |
| 私有配置 | A 自己的 `.env`、密码和镜像版本 | B 自己的 `.env`、密码和镜像版本 |

选择与实际环境对应的入口：

| 拓扑 | 首次部署入口 | 前提 |
| --- | --- | --- |
| 两角色在同一宿主机、同一 LAN | `./deploy.sh`，使用 `compose.yaml` | 根 Compose 在同一 Docker Engine 内检查 gateway 健康状态 |
| 两台宿主机、同一二层 LAN | B 执行 `./deploy.sh gateway`；A 执行 `./deploy.sh workstation` | 使用 `compose.gateway.yaml` / `compose.workstation.yaml`；分别设置各自的 `LAN_INTERFACE`；251 与 250 的地址属于同一 LAN，251 能直接到达 250 |
| 两台宿主机、不同网段或经 VPN 互通 | B 使用网关入口；A 执行 `./deploy.sh workstation-bridge` | A 使用 `workstation/compose.yaml` 的 bridge 网络，经 `WORKSTATION_HTTP_PROXY` / `WORKSTATION_HTTPS_PROXY` 指向可达的网关私有端点 |

两个独立入口没有跨宿主机的 `depends_on`、共享 Docker bridge 或 Docker 服务名解析。分开部署时先验收 B 的网关，再启动 A；可用性必须通过 A 到网关的真实请求验证。

**不同网段的边界：** macvlan 的默认网关必须在本地二层网络，不能直接把远处的 `250` 填进 A 的 IPAM 网关。bridge 模式保留 A 的正常路由；先核实已有私网/VPN/受控隧道确实能把流量送达网关容器的代理监听地址，再配置例如 `WORKSTATION_HTTP_PROXY=http://实际私有地址:7890` 和对应 HTTPS 代理。B 的宿主机地址不自动等于网关容器的代理端点；Docker 的 `172.*` bridge 地址也不自动能被 A 路由。bridge 模式不自动接管 DNS、UDP 或整机出口；有这些要求时单独确认路由设计。默认 SSH/VNC 端口仅绑定 A 的 `127.0.0.1`，通过到 A 的 SSH 隧道访问，不为此开放公网代理或 VNC。

每台主机单独保存仓库与 `.env`。`deploy.sh` 在所有入口都执行相同的已有容器保护；后续命令必须继续使用本次实际选择的 Compose 文件与 `.env`，避免误用根 Compose 启动另一角色。

## 1. 确认目标，先只读盘点

LAN 部署环境为 **Linux amd64 Docker Engine**，要求 **Docker Compose 2.33.1 或更新版本**、macvlan 及可用的物理 LAN 接口；网关还需要 `/dev/net/tun`。工作站 bridge 模式不需要 macvlan 或 TUN，但仍须使用支持镜像桌面与浏览器沙箱的 Linux amd64 Docker 环境。这套 LAN 方案不以 macOS / Windows 的 Docker Desktop 虚拟网络为部署目标。确认正在操作用户指定的主机与 Docker context，远程终端不要误用本机 Docker。分开部署时，下列盘点在 A/B 上分别执行。

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

上述地址只有在现场网络匹配且地址空闲时才使用。LAN 模式采用其他网段时，一并调整 `LAN_SUBNET`、`LAN_PREFIX`、`LAN_ROUTER`、角色地址和必要的 `WORKSTATION_NO_PROXY`，不要只替换一个 IP。分开部署时各宿主机使用自己的实际网络参数；工作站 bridge 模式的网关地址通过可达私有代理端点配置。保留 Compose 所需的设备与安全设置，不用 `privileged`、宿主网络或 Docker socket 代替正常配置。

Docker 的 `data-root` 属于宿主存储设置。**默认不迁移 Docker 数据目录、不改宿主网络、不向公网开放端口。** 如果 SSD 尚未用于 Docker，先报告实际位置、空间及影响；只有用户明确授权后，才另行安排涉及所有受影响容器的存储迁移和回退。容器内部保存业务数据，不代表这些字节脱离宿主 Docker 存储。

### 2.1 工作站国家、语言和时区初始化

这些参数仅控制 **251 容器内部** 的地区格式、界面语言和时区；宿主机地区与公网出口由各自配置决定。国家使用大写两位 ISO 代码，语言使用小写两位或三位 glibc 语言代码；初始化将两者组合成 `语言_国家.UTF-8` 并按需生成 locale，时区使用有效 IANA 名称。国家与时区并非一一对应，修改地区时明确填写全部三项。

```dotenv
# 默认：新加坡、英文
WORKSTATION_COUNTRY=SG
WORKSTATION_LANGUAGE=en
WORKSTATION_TIMEZONE=Asia/Singapore

# 例如台湾繁体中文：TW / zh / Asia/Taipei
# 例如美国英文（纽约）：US / en / America/New_York
```

只使用镜像中 `/usr/share/i18n/locales` 支持的语言/国家组合。无效代码、缺失的 locale 或时区会让初始化明确失败，AI 应修正配置后重试，不回退成另一地区。以 `WORKSTATION_*` 三项为输入，初始化统一设置 `LANG`、`LANGUAGE`、`LC_ALL`、`TZ`、`/etc/default/locale`、PAM 环境、登录 Shell 和桌面会话；不要另设互相矛盾的 `LANG` / `TZ`。此行为要求镜像已包含 `/etc/workstation/region.py`；核对所选镜像的构建/发布版本，不把当前源码改动说成已有 `latest` 镜像功能。

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

新镜像包含 `/usr/local/bin/reset-claude-user`，源码为 `workstation/scripts/reset-claude-user.py`。此命令供用户主动更换账号或清理本地身份时使用，安装、启动、重启和升级都不自动调用它；不因安装验收而删除用户的真实身份。

在 251 普通用户 `dev` 的终端执行 `reset-claude-user` 先预览；关闭 Claude 后，显式执行 `reset-claude-user --apply` 才修改文件。从 **工作站宿主机 A** 执行的等价示例：

```sh
workstation_compose=compose.workstation.yaml  # 替换为该部署实际使用的文件
docker compose --env-file .env -f "$workstation_compose" exec -T \
  --user 1100:1100 -e HOME=/home/dev workstation reset-claude-user
# 用户要求执行清理且 Claude 已关闭时：
docker compose --env-file .env -f "$workstation_compose" exec -T \
  --user 1100:1100 -e HOME=/home/dev workstation reset-claude-user --apply
```

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

编辑 `.env`，填入已经核实的 LAN 配置、镜像和初始密码。默认使用仓库提供的 GHCR 镜像；需要固定版本时，选择对应 Actions 已成功发布的 `sha-<完整提交号>` 标签，并记录实际拉取的镜像摘要。不要把未完成的构建或仓库中的示例值说成当前已验证发布。

密码处理要求：

- `.env` 只保存在目标部署的私有目录，权限为 `600`；不提交 Git，不写入公开日志、截图、命令参数或交付报告。
- 不使用 `cat .env`、`set -x`、不带 `--quiet` 的 `docker compose config` 来展示配置。通过私密输入或本地安全编辑填写密码，日志只记录“已设置”。
- 设置自己的 Web、网关 SSH、工作站 SSH 与 VNC 密码，不直接沿用示例 `admin`。VNC 密码受协议限制，为 **1–8 个 ASCII 字符**；通过私有 LAN、Tailscale 或 SSH 隧道使用。工作站 root 默认锁定，无明确需求时保持该设置。
- 网关 Web 密码仅用于新容器首次初始化，后续通过网页账户设置修改。个人代理订阅、Tailscale、Claude、Codex 和 GitHub 授权由用户配置，不导入其他部署的身份。

选择当前主机需要的部署角色后，由入口先执行不回显的配置检查和已有容器检查，再创建：

```sh
set -eu
deployment_role=all  # 按第 0 节选择 all / gateway / workstation / workstation-bridge
./deploy.sh "$deployment_role"
```

`deploy.sh` 在拉取镜像前检查本 Compose 项目是否已有容器，包括停止的容器。它拒绝执行时，保留原容器，回到已有环境评估；不要绕过防护改用 `compose up`。部署失败先检查相关容器状态和有限日志，查明原因后修复，不用删除数据、重置宿主 Docker 或反复重建代替诊断。

## 4. 在实际环境验收

从真实 LAN 客户端和容器内部分别验证。macvlan 的宿主访问限制不等于 LAN 服务故障；先区分访问来源，再检查 control bridge 或宿主防火墙。只执行当前部署需要的检查，复用仍有效的结果。

| 检查 | 必须确认的实际结果 |
| --- | --- |
| 容器、镜像与网络 | 同机部署应有 `gateway` 与 `workstation` 两个角色；分开部署时 B 只有 gateway、A 只有 workstation。包含停止容器一起核对，记录各自宿主总数、镜像 ID / digest、网络与健康状态，保留其他项目。 |
| 内部数据 | 在各自宿主机检查实际容器的 `Mounts` 与镜像 `Config.Volumes`，确认没有外置业务挂载或匿名业务卷。设备映射按所选 Compose 单独核对。 |
| 网关 Web | 实际打开主页并登录，检查控制面板及服务入口；`/healthz` 成功只说明健康接口可用。 |
| DNS | 客户端明确向网关查询 `home.arpa`，结果为本次网关 IP；再查询外部域名。确认需要使用本地域名的客户端实际采用该 DNS，而不是被加密 DNS 绕过。 |
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

## 5. 已有环境、升级与数据恢复

**重启同一个容器保留内部数据；删除、`compose down`、强制重建或替换容器会失去原容器可写层。** `docker compose restart` 不会把新的镜像或已修改的 Compose 环境变量应用到已有容器。

已有环境先确定容器 ID、角色、数据路径和身份，再选择继续使用、修复或有计划地迁移。未经明确授权，不删除旧容器、镜像、网络、缓存或原挂载数据，不执行全局 `prune`。清理应基于明确的无用清单，并在新环境的数据与业务复验完成后执行。

替换镜像前停止相应业务、导出私有数据，按文档恢复并验证。完整私有快照用于恢复原软件环境；把应用状态迁入新公开镜像需要核对路径、UID/GID、权限和账号差异。仅复制一个 HOME 不代表迁移了全部系统账号、SSH 身份及服务配置。

- [网关：数据、备份和升级](gateway/README.md#数据备份和升级)
- [工作站：数据、备份与恢复](workstation/README.md#数据备份与恢复)

私有备份和运行容器快照含身份及凭据，不进入公开源码、GHCR 镜像或附件。两个使用相同 LAN IP 或 Tailscale 身份的实例不可同时运行。迁移与清理范围超出用户已授权的首次安装时，先说明具体影响，再取得相应授权。

## 6. 最终交付给用户

用简短结果报告和验收清单交付：

- **实际入口**：网关 Web / DNS 地址、工作站 SSH / VNC 地址、账号名及密码的私有保存方式；报告不包含密码。
- **部署身份**：使用的仓库提交、镜像标签和摘要、两个角色各自的宿主机和 Compose 文件、容器名称 / ID / 状态，以及各宿主容器总数；解释保留的其他项目。
- **数据位置**：确认业务数据在各自容器内部、实际挂载检查结果、宿主 Docker 存储位置及是否 SSD；说明本次是否改过宿主设置。
- **验证结果**：逐项列出 PASS、FAIL、NOT RUN、需用户登录或不适用，并给出简短实际证据；不将待登录服务或未测模型调用写为 PASS。
- **日常操作**：同容器启停 / 重启方式、内部数据生命周期及上述备份恢复链接；说明后续升级前必须处理数据。
- **剩余事项**：需要用户完成的账号授权、路由批准、客户端设置或未解决问题。仅在全部所需验收通过时报告安装完成；仍有缺口则准确说明已完成范围。
