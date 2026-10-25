# 工作站固定出口与独立 DNS

这是可选的运维功能：把一个 LAN 工作站的公网流量和 DNS 固定到现有的具体代理节点，同时保留网关其他设备的公共 DNS、代理组和按地区分流。镜像默认不启用此功能。地区、语言设置不决定出口国家，实际国家由所选代理和现场测试确认。

## 前提

- 先按 `AI-INSTALL.md` 检查两端实际容器，保留 HOME、账号和内部数据；不要为此重建个人容器。
- 使用 Linux amd64 LAN 拓扑，Mihomo TUN 已正常运行且处于 rule 模式。工作站以该网关为默认出口，保留网关的直出拒绝规则、工作站的 NET_ADMIN/NET_RAW 能力限制。额外 bridge 必须由宿主隔离。仅设置 HTTP_PROXY 的 bridge 拓扑不能证明所有应用都受控。
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

指定来源的子规则放在通用地区规则之前，公网 MATCH 固定到具体节点，后接来源 REJECT 兜底；回环、LAN、私网及本地域名例外保留。拒绝把代理组或 DIRECT 当作固定出口。候选配置先通过 Mihomo 校验，再热加载；失败时恢复原配置。命令输出 root 私有备份目录。

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
