# AI Workstation 与家庭网关

同一仓库维护两个独立的 Linux amd64 容器：

| 服务 | 默认局域网地址 | 镜像 | 源码 |
| --- | --- | --- | --- |
| 家庭网关 | `192.168.1.250` | `ghcr.io/crazyniu/ai-workstation-gateway` | [gateway](gateway/) |
| 开发工作站 | `192.168.1.251` | `ghcr.io/crazyniu/ai-workstation` | [workstation](workstation/) |

网关内置 Mihomo、Clash 面板、AdGuard Home、Tailscale 与桌面式 Web 后台。工作站提供 XFCE、Chrome、VS Code、Godot、Codex、Claude、GitHub CLI 与本地 MCP 工具。镜像不包含个人代理节点、订阅、登录身份或业务数据。

## 一键部署

在接入局域网的 Linux / NAS Docker 主机上执行。需要 Docker Compose v2 和 macvlan 支持；Docker Desktop 的默认虚拟网络不适用这套局域网地址方案。

```sh
git clone https://github.com/crazyniu/ai-workstation.git
cd ai-workstation
cp .env.example .env
# 编辑 .env 中的网卡、上游路由、未占用的地址和初始密码
./deploy.sh
```

两台容器同时创建，工作站默认通过网关访问外部网络。网关与宿主机通过独立的 control bridge 通信；NAS 地址可填写 `HOST_ADDRESS`。macvlan 默认不能直接访问宿主机，网关通过 control bridge 到 `HOST_ADDRESS` 的路由为工作站转发 NAS 访问；请设置实际 NAS 地址。工作站桌面和 CLI 默认显式使用网关 7890 代理，局域网地址绕过显式代理。

| 入口 | 默认账号 / 密码 |
| --- | --- |
| 网关 Web `http://192.168.1.250/` | 密码 `admin` |
| 网关 SSH `192.168.1.250:22` | `admin` / `admin` |
| 工作站 SSH `192.168.1.251:22` | `dev` / `admin` |
| 工作站 VNC `192.168.1.251:5901` | 密码 `admin` |

Web 密码在容器首次启动时读取 `WEB_PASSWORD`，之后在“设置 → 账户”修改；重启保留保存的密码。网关 SSH 账号密码由 `GATEWAY_USER`、`GATEWAY_PASSWORD` 管理，修改 `.env` 后重建该容器生效。工作站密码由 Compose 中的 `WORKSTATION_PASSWORD`、`VNC_PASSWORD` 设置。VNC 密码接受 1–8 个 ASCII 字符。工作站 root 默认锁定，可通过 `WORKSTATION_ROOT_PASSWORD` 设置。账号、数据、SSH 主机密钥均按各服务说明持久化。

让客户端实际使用网关 DNS `192.168.1.250` 后，可以通过 **http://home.arpa** 打开主页。域名解析不会替客户端修改默认网关；需要代理整个设备时，将设备网关也设置为 `.250`。DNS 与 IP 入口始终保留。

## 使用

- 首页默认入口为 Clash、AdGuard Home、Tailscale 和设置。右键桌面可添加链接；右键图标可编辑和排序。
- 在代理设置上传 Clash / Mihomo YAML 文件，校验后保存应用。节点选择、测速和连接记录使用 Clash 面板。
- 广告过滤使用 AdGuard Home 页面；首次启动已带本地过滤规则。
- Tailscale 首次启动未登录，在设置中登录后自动识别并发布网关所在的内网子网，同时接收其他设备的子网路由。页面自动更新连接状态；若账号未设置自动批准，页面会提示管理员批准路由。
- 设置包含桌面管理、壁纸、亮色 / 暗色 / 自动主题、账户、逐项服务升级及备份恢复。
- 两个容器均已安装 `gh`。通过 `ssh` 登录后运行 `gh auth login`，使用自己的 GitHub 账号；工作站也可执行 `docker compose exec --user 1100:1100 -e HOME=/home/dev workstation gh auth login`。凭据写入各自容器内部 HOME。Codex / Claude 登录同样由各用户完成。

```sh
docker compose ps
docker compose logs --tail 100 gateway
docker compose exec workstation gh --version
# 镜像升级会重新创建容器，先按各服务说明导出并恢复内部数据
```

升级网关内的 Mihomo / AdGuard / Tailscale / Clash 面板可在 Web 内完成，程序与配置保存在容器内部 `/data`，失败会恢复旧版本。网关后台、Nginx、Python 和基础系统随镜像替换升级。

## 数据与镜像升级

两个服务均不声明业务 bind mount 或 Docker volume；配置、HOME、账号状态保存在容器写入层，随 Docker 存储留在 SSD。`docker restart` 保留数据，删除或重建容器会丢失内部数据。替换镜像前先停服务并导出私有数据备份，再创建新容器、恢复数据并启动验证。网关 `/data` 与工作站 HOME、SSH keys 及运行时代理配置的导出方法见各服务说明。完整业务容器可另用 `docker commit` 和 `docker save` 保存私有恢复镜像，个人数据镜像不得发布到 GHCR。

## 构建与验证

```sh
python3 -m pip install PyYAML
python3 gateway/scripts/fetch-components.py amd64
docker build --build-arg TARGETARCH=amd64 -t gateway-local:test gateway
python3 -m unittest discover -s gateway/tests -v
bash gateway/tests/clean-smoke.sh gateway-local:test
docker build -t workstation-local:test workstation
bash workstation/tests/smoke.sh workstation-local:test
```

GitHub Actions 分别构建两个镜像，通过隔离启动、关键行为和镜像层检查后推送 GHCR。首次发布前 `latest` 可能尚不存在，以实际 Actions 结果为准。

公开 Compose 创建的是空白环境，已有账号和 HOME 需要单独迁入目标容器。当前部署只保留 `.250` Clash 网关和 `.251` Claude 开发工作站；Hermes、WorkBuddy 及旧测试容器已移出交付范围。切换期间保留原容器用于失败回退，最终数据、网络和重启验收通过后清理原容器及迁移暂存。私有迁移资料、原始配置、离线镜像和验收记录不提交到 Git。

许可、第三方组件来源和详细说明见 [网关说明](gateway/README.md)、[工作站说明](workstation/README.md)。
