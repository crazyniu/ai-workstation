# 工作站固定出口与独立 DNS

## LAN 访问与可选隔离

默认部署由工作站直接持有 251 地址，可以主动连接同一局域网的 Mac，包括 Orca 配对地址使用的 WebSocket 服务。Mac 主动通过 SSH 连接 251 也使用这条局域网。固定公网代理的故障保护独立生效。

从 251 打开 `http://192.168.1.250/transfer/` 可直接上传或下载文件，MCP 客户端使用 `http://192.168.1.250/api/transfer/mcp`。自定义 LAN 地址时使用实际网关 IP。网关对配对工作站的 Web 访问只开放互传页面、静态资源和文件接口，访问桌面、Clash 和管理 API 返回 403。工作站会把网关 IP 加入 `NO_PROXY`。

### 显式启用隔离

选择隔离并为必需的内网服务准备目标端口后再启用。新环境同机安装用 `./deploy.sh all --isolate-lan`，分机分别用 `./deploy.sh gateway --isolate-lan` 和 `./deploy.sh workstation --isolate-lan`。后续 Compose 管理须在原 `-f` 参数后追加对应角色的 `-f compose.gateway-isolation.yaml` 或 `-f compose.workstation-isolation.yaml`，同机隔离使用两者。

隔离部署中，`workstation-network` 持有工作站的 IPv4 地址。它先在工作站网络命名空间装载 nftables，再允许桌面和 SSH 启动。工作站没有 NET_ADMIN、NET_RAW，也没有辅助容器的文件系统。保留本机回环和已建立的入站管理会话回包。对 250 开放 TCP 53、80、7890、7891 及 UDP 53。其他内网设备仅接受管理员明确放行的目标 IPv4、协议和端口。其余私有地址、链路本地、组播和 IPv6 的主动连接受阻。正常管理连接的对端地址和默认网关仍可见。

250 对受隔离来源优先拒绝本地域名和内网目的地址。允许访问公网的 DIRECT 规则使用独立的套接字标记，防火墙按最终拨号地址再判一次。含不受限制的 DIRECT 或全量静态节点的共享组对该来源按拒绝处理；可显式选择单个节点。AdGuard 的来源过滤覆盖本地域名及内网反查。管理口、直出转发和保护规则均位于业务工作站之外。

### 放行 Orca 或其他设备端口

在工作站桌面或 SSH 中打开 **niu.sh → 7**。菜单显示已保存的出站规则及隔离状态。用 **1** 选择同一局域网内已配对的 Orca WebSocket 端点，用 **2** 输入其他设备的 IPv4、目标端口及 TCP 或 UDP，用 **3** 移除一条规则。需要管理员权限。隔离开启时即时更新内核规则，关闭时可提前保存。若同步失败，菜单会提示，用 **4** 重新应用。

规则保存在业务容器的 `/etc/workstation/lan-ports.json`。启动时先装载规则，再启动应用。首次部署也可以在工作站私有 `.env` 填入 `WORKSTATION_INITIAL_ORCA_ENDPOINT=<Mac IPv4>:<TCP 端口>`。初始值只在没有已保存文件时使用，主动移除的端口不会在重启后被再次添加。

例外用于 251 直接连接同网段设备，不开放任何入站端口。250 自身的访问策略仍然有效，应用若强制经过 250 的 HTTP 代理，需要为目标地址设置直连。已批准的地址会加入新登录 shell 和启动应用的 `NO_PROXY`。已经运行的应用沿用已有环境，可在该应用内设置代理例外或在新会话中重新打开。

### HTTP 出口故障

Clash 控制面板编辑、下载的是 `mihomo/config.yaml`。网关在启动和每次应用时，从它生成 `.gateway-effective.yaml` 并交给 Mihomo。用具体的 HTTP、HTTPS 或 SOCKS5 节点作为软件规则或来源绑定的目标。TCP 拨号失败即失败，不改走 DIRECT。不支持 UDP 的匹配策略带有同条件的拒绝兜底，主规则和子规则均适用。包含显式固定出口的自动组在运行配置中使用手动选择，空组拒绝。保护生效时使用 rule 模式，修改配置经网关控制面板，节点选择仍可在节点面板操作。

通过规则集选一批订阅节点和手动固定到某一个节点有不同语义。仅包含动态订阅的自动组仍按原策略选择可用节点。需要约束整个远端应用时，要覆盖它的全部连接；网关通常看不到另一台主机上的进程名，可按来源 IP 绑定，并将绑定置于更宽的直连规则之前。需要固定某个出口的软件应直接指定节点。网关约束经过它的流量，其他客户端自行改用别的网络需要客户端或上游网络策略约束。

### 迁移与验收

从旧镜像启用隔离模式下的文件互传时，先升级 250 网关镜像，再升级 251 的工作站及网络辅助容器。两端的网络规则随容器镜像交付。

从普通 LAN 切换到隔离模式时，分机部署须分别更新网关和工作站，旧容器简单重启不会得到新网络命名空间。移除旧部署附加的 Docker 网桥与指向内网设备的静态路由，不将它们带入辅助容器。已有部署先保存工作站 HOME、SSH 身份、原镜像和 Compose，以及网关私有数据，按用户批准的迁移窗口更换。验收由用户分别检查：从管理端连入 251；从 251 直连已放行的 Orca 配对端口应成功，连接同设备其他未放行端口或 NAS 应失败；通过 250 代理请求 NAS 也应失败；公网请求应命中指定出口。在维护窗口将测试出口设为不可达，确认同一软件的 TCP、UDP 均无直连，再恢复该出口。不要为验收停掉所有客户端共用的网关。

## 可选的工作站专用 DNS 与固定节点


这是可选的运维功能：把一个 LAN 工作站的公网流量和 DNS 固定到现有的具体代理节点，同时保留网关其他设备的公共 DNS、代理组和按地区分流。镜像默认不启用此功能。地区、语言设置不决定出口国家，实际国家由所选代理和现场测试确认。

## 前提

- 先按 `AI-INSTALL.md` 检查两端实际容器，保留 HOME、账号和内部数据；不要为此重建个人容器。
- 使用支持所选组件和内核功能的 Linux LAN 拓扑，Mihomo TUN 已正常运行且处于 rule 模式。工作站以该网关为默认出口，保留网关的直出拒绝规则、工作站的 NET_ADMIN/NET_RAW 能力限制。额外 bridge 必须由宿主隔离。仅设置 HTTP_PROXY 的 bridge 拓扑不能证明所有应用都受控。
- 此命令不创建宿主防火墙或路由规则，需要先满足以上前提。
- 工作站需要当前版本的 root 专用 Supervisor socket 及 `/etc/supervisor/conf.d/*.conf` include。旧镜像缺少这些入口时单独安排保留数据的升级，安装器不会重启桌面。
- 网关与工作站 LAN 地址互通；工作站的 TCP/UDP 5354 与回环 TCP 3001 空闲。

以下沿用 README 的角色地址示例，替换容器名、IP 和 `AI-HTTP` 节点名称。分宿主部署时分别在对应 Docker context 执行。无需导出或打印含凭据的完整代理配置。

## 按顺序配置

先在网关预览工作站的源地址规则，默认只读；确认预览后添加 `--apply`：

```sh
docker exec --user 0 gateway-250 python3 /opt/gateway/app/workstation_dns.py route \
  --source-ip 192.168.1.251 --exit-proxy AI-HTTP
docker exec --user 0 gateway-250 python3 /opt/gateway/app/workstation_dns.py route \
  --source-ip 192.168.1.251 --exit-proxy AI-HTTP --apply
```

指定来源的子规则放在通用地区规则之前，公网 MATCH 固定到具体节点，后接来源 REJECT 兜底；源文件保留已有本地例外；显式启用的 LAN 隔离策略优先拒绝 251 对内网的主动访问。拒绝把代理组或 DIRECT 当作固定出口。候选配置先通过 Mihomo 校验，再热加载；失败时恢复原配置。命令输出 root 私有备份目录。

已有正确的源地址固定规则可以保留；下面的 DNS 命令会校验它的优先级、固定出口和 REJECT 兜底。

在工作站预览并安装独立解析器：

```sh
docker exec --user 0 workstation-251 configure-workstation-exit-dns \
  --source-ip 192.168.1.251 --gateway-ip 192.168.1.250
docker exec --user 0 workstation-251 configure-workstation-exit-dns \
  --source-ip 192.168.1.251 --gateway-ip 192.168.1.250 --apply
```

安装器从固定公开版本下载 AdGuard Home，校验压缩包和可执行文件的 SHA256，并保留上游许可证。服务以已有 nobody 账号运行，不新增能力或挂载；配置和工作数据位于容器内部。管理入口仅监听回环，使用随机口令的 BCrypt 哈希。发现已有解析器文件时拒绝覆盖。Supervisor 只增加新进程，现有 SSH 和桌面程序继续运行。

专用解析器使用 `https://1.1.1.1/dns-query` 和 `https://8.8.8.8/dns-query`，保留 TLS 校验，bootstrap/fallback 列表为空，关闭 HTTP/3 上游。IP 地址形式不需要启动域名解析；DoH 连接遵循工作站的固定出口规则。解析器仅允许网关和 localhost 查询。

最后只切换该来源的 AdGuard 客户端：

```sh
docker exec --user 0 gateway-250 python3 /opt/gateway/app/workstation_dns.py dns \
  --source-ip 192.168.1.251 --exit-proxy AI-HTTP
docker exec --user 0 gateway-250 python3 /opt/gateway/app/workstation_dns.py dns \
  --source-ip 192.168.1.251 --exit-proxy AI-HTTP --apply
```

网关先验证运行模式和解析器可用性，再通过 AdGuard 客户端 API 为该来源设置 `tcp://192.168.1.251:5354`。全局广告过滤保留在解析器前。已有 home.arpa、lan、local、Tailscale 域名例外仅在其上游为私网地址时保留；该客户端的公网域名专用上游会被移除。共享或不明确的客户端标识直接拒绝，防止连带修改其他设备。

## 验证

从工作站使用多个独立服务检查公网 IP，访问境内、境外站点，并核对 Mihomo 实时连接链：应用和 DoH 连接应命中固定出口。经正常解析路径查询权威 DNS 诊断域名，检查解析器及 ECS 回显。

同时检查内网域名、广告过滤、浏览器 HTTPS、SSH、VNC，并从另一台 LAN 客户端验证原有解析。可短暂停止**仅该工作站的独立解析器**：新查询应失败，其他设备继续解析；随后立即恢复。不要为此停止影响其他设备的共享代理。

这不修改云端账号国家、历史登录地区或浏览器指纹；必要的私网通信保留。构建成功或一次解析成功不能代替完整出口验证。

## 回退与已有部署

使用命令输出的备份目录，先预览再加 `--apply`。先恢复 DNS 客户端，再停用专用解析器；需要恢复出口规则时最后回退 route 备份。

```sh
docker exec --user 0 gateway-250 python3 /opt/gateway/app/workstation_dns.py rollback \
  --backup /data/backups/workstation-egress-BACKUP_ID
docker exec --user 0 gateway-250 python3 /opt/gateway/app/workstation_dns.py rollback \
  --backup /data/backups/workstation-egress-BACKUP_ID --apply
```

代理配置或客户端在应用后被再次修改时，自动回退会拒绝覆盖；保留私有备份并人工协调后续改动。DNS 回退只恢复该客户端，route 回退仅在应用后文件哈希仍相符时恢复原文件。

恢复 DNS 客户端之后，只停止和停用新服务：

```sh
docker exec --user 0 workstation-251 supervisorctl -c /etc/supervisor/supervisord.conf \
  stop workstation-exit-dns
docker exec --user 0 workstation-251 mv /etc/supervisor/conf.d/workstation-exit-dns.conf \
  /opt/workstation-exit-dns/supervisor.conf.disabled
docker exec --user 0 workstation-251 supervisorctl -c /etc/supervisor/supervisord.conf reread
docker exec --user 0 workstation-251 supervisorctl -c /etc/supervisor/supervisord.conf \
  update workstation-exit-dns
```

整个流程不删除个人数据或重新创建容器。已在现场手工配置且正常运行的同类服务应先检查并保留，不重复安装。
