# AI Workstation & Gateway

[![Container images](https://github.com/crazyniu/ai-workstation/actions/workflows/images.yml/badge.svg)](https://github.com/crazyniu/ai-workstation/actions/workflows/images.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

面向家庭网络与远程开发的双容器环境：一个带桌面式 Web 后台的网关，一个可通过 SSH / VNC 使用的 Linux 开发工作站。

![AI Workstation 与网关桌面展示](docs/images/gateway-home-ai.png)

*基于真实主页截图生成的 AI 示意图；实际界面以运行版本为准。[图片来源与生成说明](docs/images/README.md)*

## 两个服务

| 服务 | 默认地址 | 能力 | 公开镜像 |
| --- | --- | --- | --- |
| Gateway | `192.168.1.250` | Mihomo / Clash、AdGuard Home、Tailscale、Web 控制面板 | `ghcr.io/crazyniu/ai-workstation-gateway` |
| Workstation | `192.168.1.251` | XFCE、Chrome、VS Code、Godot、Codex、Claude、GitHub CLI、MCP 工具 | `ghcr.io/crazyniu/ai-workstation` |

- 桌面链接支持自动获取站点 favicon，也可手动选图标；提供壁纸、主题、排序与账户设置。
- 网关统一管理代理配置、DNS、子网访问、组件升级与备份恢复。
- 工作站的桌面和 CLI 默认经网关代理访问外网，局域网地址绕过显式代理。
- 配置、HOME 和账号身份全部保存在各自容器内部。公开镜像包含程序和默认模板，个人订阅、身份和业务数据由用户自行配置。

## 首次部署

需要接入局域网的 **Linux amd64 主机**、Docker Engine、**Docker Compose 2.33.1 或更新版本**、macvlan 支持和 `/dev/net/tun`。提前为两个容器保留未占用的 LAN 地址。Docker Desktop 默认虚拟网络不适用于这套地址方案。

```sh
git clone https://github.com/crazyniu/ai-workstation.git
cd ai-workstation
cp .env.example .env
chmod 600 .env
# 编辑 .env：网卡、路由器、容器地址、初始密码，以及需要访问的 NAS 宿主地址
./deploy.sh
```

[`.env.example`](.env.example) 列出全部参数。`LAN_INTERFACE` 必须是实际 LAN 网卡；需要访问 NAS 宿主时填写 `HOST_ADDRESS`。网关使用 control bridge 到达宿主，再为工作站转发该地址的访问。

`deploy.sh` 只用于首次创建：项目已有运行中或已停止的容器时会拒绝执行，避免重新创建容器覆盖内部数据。日常重启使用 `docker compose restart`。

| 入口 | 初始账号 / 密码 |
| --- | --- |
| 网关 Web：`http://192.168.1.250/` | 密码来自 `WEB_PASSWORD`，示例值为 `admin` |
| 网关 SSH：`192.168.1.250:22` | `GATEWAY_USER` / `GATEWAY_PASSWORD`，示例均为 `admin` |
| 工作站 SSH：`192.168.1.251:22` | `dev` / `WORKSTATION_PASSWORD`，示例密码为 `admin` |
| 工作站 VNC：`192.168.1.251:5901` | `VNC_PASSWORD`，示例值为 `admin` |

部署前设置自己的密码。VNC 密码接受 1–8 个 ASCII 字符；工作站 root 默认锁定。网关 Web 密码首次初始化后由“设置 → 账户”管理。后续环境变量变更与数据处理见各服务文档。

## 开始使用

1. 打开网关主页，在代理配置中导入自己的 Clash / Mihomo YAML 并应用，通过 Clash 面板选择节点。
2. 让客户端使用网关 DNS 后，通过 `http://home.arpa` 访问主页。需要代理整个设备时，同时将该设备的默认网关设为网关容器地址。
3. 在 Tailscale 设置中登录自己的账号，并按页面提示批准子网路由。
4. 通过 VNC 打开工作站桌面，或通过 SSH 登录 `dev`。在应用内完成 Codex、Claude、GitHub 等个人账号登录。

```sh
docker compose ps
docker compose logs --tail 100 gateway
docker compose exec --user 1100:1100 -e HOME=/home/dev workstation gh auth login
```

更多配置见 [网关使用说明](gateway/README.md) 和 [工作站使用说明](workstation/README.md)。

## 数据与升级

两个服务不声明业务 bind mount、命名卷或匿名卷。数据写入容器层，底层位置由宿主的 Docker `data-root` 决定；建议放在 SSD，Compose 本身不会迁移宿主存储。

**重启保留数据；删除或重新创建容器会丢失内部数据。** 替换镜像前，先停止业务、导出需要保留的私有状态，并验证恢复流程。完整私有镜像用于原环境恢复；升级到新镜像需要选择性迁移配置和用户数据。操作步骤见 [网关数据处理](gateway/README.md) 和 [工作站备份与恢复](workstation/README.md)。个人状态、恢复镜像和凭据应留在私有存储中。

网关 Web 内的组件升级会保留 `/data` 中的配置，失败时回退组件。后台代码、Nginx、Python 与基础系统通过替换镜像更新。

## 开发与验证

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install PyYAML
python3 -m unittest discover -s gateway/tests -v
python3 -m unittest discover -s tests -p 'test_deploy.py' -v
for test in workstation/tests/test-*.py; do python3 "$test"; done

python3 gateway/scripts/fetch-components.py amd64
docker build --build-arg TARGETARCH=amd64 -t gateway-local:test gateway
bash gateway/tests/clean-smoke.sh gateway-local:test
docker image save gateway-local:test | python3 gateway/tests/audit-image.py

docker build -t workstation-local:test workstation
bash workstation/tests/smoke.sh workstation-local:test
bash workstation/tests/internal-storage.sh workstation-local:test
docker image save workstation-local:test | python3 workstation/tests/audit-image.py
```

容器验证需要 Linux Docker 环境。GitHub Actions 会构建两个干净镜像，运行启动、内部存储和镜像层检查；主分支验证通过后发布 `latest` 与 `sha-<完整提交号>` 标签。使用固定 SHA 标签可选择已验证的版本。实时进度见 [Actions](https://github.com/crazyniu/ai-workstation/actions/workflows/images.yml)。

| 路径 | 内容 |
| --- | --- |
| [`gateway/`](gateway/) | Web 后台、网关运行时、组件锁定文件和测试 |
| [`workstation/`](workstation/) | 桌面环境、工具安装、启动配置和测试 |
| [`compose.yaml`](compose.yaml) | 双容器网络与运行参数 |
| [`tests/`](tests/) | 部署入口保护测试 |
| [`docs/`](docs/) | 项目展示素材与来源说明 |

欢迎提交问题和 Pull Request。开发约定见 [CONTRIBUTING.md](CONTRIBUTING.md)，漏洞报告见 [SECURITY.md](SECURITY.md)。

## 许可

仓库自有代码采用 [MIT License](LICENSE)。第三方组件、字体、编辑器依赖及随镜像安装的软件按各自许可分发；MIT 不替代这些许可。来源与素材说明见 [NOTICE](NOTICE) 和 [网关第三方清单](gateway/NOTICE)。
