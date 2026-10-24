# 验证与发布记录

工作站面向 Linux amd64 Docker Engine。以下命令从仓库根目录执行；所有运行验收使用独立临时容器，退出时清理测试容器、测试卷和随机凭据，不读取现有业务 HOME。

## 可复现验证

```sh
set -eu
for test in workstation/tests/test-*.py; do python3 "$test"; done
docker build -t workstation-local:test workstation
bash workstation/tests/smoke.sh workstation-local:test
bash workstation/tests/internal-storage.sh workstation-local:test
docker image save workstation-local:test | python3 workstation/tests/audit-image.py
```

| 检查 | 覆盖范围 |
| --- | --- |
| `smoke.sh` | 普通用户权限、桌面进程及启动器、SSH/VNC 真实认证、工具版本、本地 MCP 握手、Chrome 沙箱、重启持久性及 HOME 软链接隔离。此夹具使用临时测试卷。 |
| `internal-storage.sh` | 镜像没有 `Config.Volumes`、容器 `Mounts=[]`、运行时密码认证、HOME/CLI 配置/GitHub CLI 设置/SSH 主机密钥在重启后保留、普通用户桌面代理环境，以及默认新加坡英文／新加坡时区和内部文件修改地区后的重启验证。此夹具没有业务挂载。 |
| `audit-image.py` | 扫描 manifest 声明的全部镜像层，检查常见私人状态、认证文件、主机私钥、烘焙密码和代理环境。缺少或无法读取的层导致失败；检查结合构建允许清单使用。 |
| Python 回归测试 | 镜像审计、SSH/VNC 认证夹具、桌面 CLI 启动包装逻辑及地区配置校验/生成/优先级/失败边界。 |
| `desktop-recovery.py` | 由两个容器夹具调用：检查真实终端的标题栏边距、面板常显；暂停会话管理器并终止窗口管理器／面板，验证独立恢复、应用保持打开及无重复实例。内部存储夹具在重启后执行。 |

`tests/cli-startup.py` 是独立的真实 PTY 首次启动检查，仅在无个人登录状态的临时容器中，以普通用户执行。它观察 Codex / Claude 首次界面与持续存活，检测连接错误，不提交任何登录或模型请求。该检查需要合适的外网出口，不放入断网的 `internal-storage.sh` 夹具。

## 2026-10-24 默认地区恢复为新加坡英文

- Dockerfile 的镜像环境、预生成 locale、系统时区、三个 Compose 入口、`.env.example` 和地区初始化回退值统一为 `SG` / `en_SG.UTF-8` / `Asia/Singapore`。已有内部 `region.json` 仍优先，其他国家与语言配置继续支持。
- PASS：工作站 Python 测试与根目录部署测试；地区测试核对新加坡全年 UTC+8、登录配置和内部文件覆盖。
- Linux 镜像验收由本次 PR 和主分支 Actions 运行：`internal-storage.sh` 首次启动检查新加坡默认值，再修改内部地区并重启，核对登录、桌面、HOME 与身份持久性。以相应 Actions 运行结果及发布摘要为准。
- 下方洛杉矶记录保留为历史验收记录，当前默认值以本节与安装说明为准。

## 2026-10-24 桌面恢复与洛杉矶默认地区

- 默认国家、语言和时区统一为 `US` / `en_US.UTF-8` / `America/Los_Angeles`，同步 Dockerfile、全部工作站 Compose 入口、环境示例、初始化程序和安装说明。使用 IANA 时区处理夏令时；已有内部地区覆盖仍优先。
- 默认面板常显、窗口标题栏和最大化边框可见。新增普通用户桌面恢复程序，限定当前用户与 X11 显示，等待会话启动，并限制失败重试频率；健康检查拒绝缺失或僵尸窗口管理器。
- PASS：本地工作站 Python 回归 60 项中 59 项通过，Linux `/proc` 用例 1 项在 macOS 跳过；部署与 CI 分类回归 11 项通过。三个工作站 Compose 入口解析后的默认地区一致，Shell 语法及差异格式检查通过。
- PASS：Linux amd64 隔离运行验收使用既有本地基础环境加载本次仓库 runtime、桌面模板和测试，补装正式 Dockerfile 已声明的 `gh` 与 `x11-utils`。`internal-storage.sh` 完整通过：默认洛杉矶地区、SSH/VNC 真实认证、内部配置切换及重启、真实窗口标题栏、独立故障恢复和 HOME／SSH 身份持久性。临时容器无业务挂载并已清理。该临时验证镜像不用于发布，也不作为干净公共镜像的证明。
- PASS：现有工作站内部国家、登录环境、时区及启动初始化已统一为美国／洛杉矶；重启后检查实际普通用户登录和 XFCE 进程环境，桌面面板与标题栏正常。保留既有 HOME、身份和应用数据。
- 本次 NAS 的完整公开源镜像构建在拉取基础镜像时被宿主 Docker 的不可达旧代理阻断；干净双镜像构建、完整 smoke 与镜像层审计由 GitHub Actions 检查。宿主 Docker 网络设置保持原状。

## 2026-10-24 地区初始化与分开部署源码验证（未发布）

- PASS：工作站 Python 回归 39 项、部署入口保护回归 7 项，共 46 项；四份部署 Compose 的 `config --quiet` 及 Shell 语法检查通过。
- PASS：独立 gateway/workstation Compose 的服务设置与同机版本对应，移除了工作站对本地 gateway 的依赖，无业务挂载。
- PASS：在独立的 Linux amd64 临时容器内运行新地区初始化程序，实际生成默认 `en_SG.UTF-8`，登录用户得到新加坡英文与时区。内部 `region.json` 切换到 `en_US.UTF-8` / `America/New_York` 后，重启同一临时容器，配置与 HOME 测试数据保留，`Mounts=[]`。无效的时区文件被拒绝，原 locale 配置保持。测试容器已清理。
- PASS：后续 [PR #4 CI](https://github.com/crazyniu/ai-workstation/actions/runs/40058036946) 完成完整新镜像构建、桌面/SSH/VNC smoke、内部存储与地区变更重启验收及镜像层审计。
- NOT RUN：两台独立宿主机之间的 LAN/VPN/代理真实部署验收。Compose 配置检查与单机临时容器验证不能替代跨设备连通性验收。

本节为当前源码的验证边界；不代表该功能已包含在下面记录的历史公开镜像或当前 `latest` 中。

## 2026-10-24 Claude 身份重置源码验证（未发布）

- 新增 `reset-claude-user` 镜像安装步骤、用户与 AI 使用说明及 CCBaga MIT 来源声明。命令默认预览，启动流程不调用清理。
- PASS：本地完整 Python 回归 57 项中 56 项通过，Linux `/proc` 进程检测 1 项因本机 macOS 跳过；随后在 Linux amd64 独立临时容器以普通用户运行新增的 11 项重置测试全部通过，包括真实 Claude 进程检测。
- PASS：临时容器中的 `/usr/local/bin/reset-claude-user` 实际预览保持身份字段，执行后删除身份字段并保留 MCP 配置和 MCP OAuth 凭据。新版 `smoke.sh` 已加入同一隔离 HOME 检查；真实部署没有执行账号清理。
- PASS：Shell 语法、文档本地链接及差异格式检查。重置测试使用临时 HOME，不读取真实用户凭据。
- PASS：后续 [PR #4 CI](https://github.com/crazyniu/ai-workstation/actions/runs/40058036946) 完成包含重置安装步骤的完整新镜像构建与全流程 smoke；镜像发布状态以对应主分支发布流水线为准。

## 2026-10-24 Unity Personal 与 MCP

- PASS：固定 Unity Editor `6000.3.27f1` 官方 Linux 安装包，上游发布 API 的 MD5 校验通过，再记录完整文件 SHA256；Hub `3.22.4`、uv `0.13.5` 和 Unity MCP `10.3.0` 均验证固定来源及校验值。
- PASS：现有 Linux amd64 工作站内安装 Editor、Hub、本地 MCP 服务和项目桥接包；普通用户执行 `unity-editor -version` 返回 `6000.3.27f1`，Hub CLI 正常显示帮助。
- PASS：Claude `mcp get unity` 显示 Connected；独立 MCP SDK 完成 stdio 握手，枚举 48 个工具、18 项资源。现有五个 MCP 及其他 Claude 设置逐项比较保持一致；Codex 也追加 Unity MCP。
- PASS：通过 macOS 屏幕共享打开实际桌面启动器，按用户明确授权接受首次 Unity 软件条款并进入 Hub 登录流程。准备了独立空白项目及本地桥接包引用。
- PASS：工作站 Python 回归 53 项与仓库部署/CI 分类回归 11 项；其中 Linux `/proc` 进程检测 1 项在 macOS 跳过。新增测试覆盖追加 Unity MCP、保留既有身份与同名覆盖、重复安装和配置权限；Shell/JavaScript 语法及差异格式通过。
- 修复首次 PR CI 的版本误判：官方 uv 输出包含平台元数据，版本检查现接受 `uv 0.13.5 (x86_64-unknown-linux-gnu)`，同时拒绝不同版本；增加失败时的实际版本输出。已验证带/不带元数据及相邻错误版本四种情况。
- NOT RUN：Unity 账号登录、Personal 免费许可证激活、项目导入及真实场景读写尚未验证。需要用户登录自己的 Unity 账号；MCP 服务端 Connected 不等于编辑器桥接已连接。
- PASS：[PR #5 最新 CI](https://github.com/crazyniu/ai-workstation/actions/runs/40072479711) 的四项检查全部通过：双镜像构建、工作站完整 smoke、Unity MCP 48 工具枚举、沙箱浏览器、SSH/VNC 认证、HOME/SSH 身份/地区变更重启持久性，以及工作站全部 18 层镜像审计。GitHub 随后自动合并至 `main`；已有工作站未重建或重启。Editor/Hub 为独立可选安装，不包含在默认公共镜像中。

## 已验证的公开发布

[GitHub Actions 运行 39958308949](https://github.com/crazyniu/ai-workstation/actions/runs/39958308949) 于 2026-10-23 对提交 [`948e9d897f6bed47448a8eacdcfeffc9e9fa0ba4`](https://github.com/crazyniu/ai-workstation/commit/948e9d897f6bed47448a8eacdcfeffc9e9fa0ba4) 完成双镜像流水线。工作站的干净构建、`smoke.sh`、`internal-storage.sh` 和全部 16 层镜像审计成功，随后发布到 GHCR。

工作站提交标签：

```text
ghcr.io/crazyniu/ai-workstation:sha-948e9d897f6bed47448a8eacdcfeffc9e9fa0ba4
```

该发布的 manifest 摘要：

```text
sha256:5fd1edc6d5309d5939da83a2c52111a90a8d4e4b88d5d8b6eb4ff7eb5f75559f
```

发布后匿名授权读取该提交标签与当时的 `latest` manifest 均返回 HTTP 200，响应摘要与 manifest 内容 SHA256 一致。此处记录固定提交的验证结果；`latest` 会随后续发布移动，后续版本以对应 Actions 运行和提交标签为准。

## 验证边界

- 桌面进程、SSH/VNC 协议认证和 PTY 启动不能代替不同客户端上的完整鼠标键盘使用流程。
- 镜像不带个人登录。GitHub、Codex、Claude 个人授权和模型服务侧调用不属于上述干净镜像验收。
- Tailscale peer 双向访问、实际代理出口、LAN/NAS 路由与客户端 DNS 依赖部署环境，需要部署后核验。
- 本地 MCP 握手和工具枚举不等于外部文档查询、GitHub 账号访问、实际 Godot 项目性能或 VS Code 项目工作流已经通过。

个人部署的 IP 切换、数据迁移清单、磁盘路径、截图与原始日志不作为公共项目的发布记录提交。

## noVNC 网页桌面验收

- `web-desktop.py` 通过真实 HTTPS/WebSocket/RFB 连接检查页面、来源限制和认证方式；跨站或缺少 Origin 的 WebSocket 应拒绝。
- `internal-storage.sh` 在默认密码模式下运行网页握手验收，继续保留已有 SSH/VNC 正确与错误密码测试。
- `web-desktop.sh` 创建无业务挂载的隔离容器，不提供 VNC 密码，验证显式免密码模式；重启后复查网页桌面和 TLS 证书身份。
- 本地 Python 与部署测试、Shell 语法检查通过。真实 Linux 容器、镜像隐私审计与发布结果以相应 Actions 为准；浏览器图形界面和中文剪贴板另在实际部署中验收。
