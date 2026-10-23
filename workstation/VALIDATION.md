# 工作站验收记录

## 最终拓扑现场验收：2026-10-23

本节记录 2026-10-23 20:32（Asia/Taipei）清理完成时的现场结果。最终运行容器为 `gateway-250`（`192.168.1.250`，Clash 网关）和 `workstation-251`（`192.168.1.251`，Claude / Codex 工作站）。现场工作站保留了原有用户数据；公开镜像继续从本仓库的干净 Dockerfile 构建，现场容器和私人数据不作为分发镜像。

| 验证 | 实际结果 |
| --- | --- |
| 容器与存储 | `docker ps -a` 仅有两个最终容器，均为 running，二者 `Mounts=[]`。Docker 存储仍在 SSD；存储守卫检查通过。 |
| 数据迁移 | 工作站 HOME 的 22,831 项、网关数据的 608 项通过迁移清单核对；重启后状态保留检查通过。 |
| 旧资源清理 | 原网关、原工作站、实验网关和两个测试容器已删除；五个旧卷和三个废弃网络已删除；旧业务挂载计划和迁移暂存已移除。清理后仅有两个在用镜像、零业务卷和零构建缓存。 |
| LAN 与域名 | 网关网页 HTTP 200；UDP/TCP DNS 均将 `home.arpa` 解析到 `.250`；客户端系统 DNS 与域名网页 HTTP 200。`.250` / `.251` SSH 和 `.251` VNC 服务握手通过。此项不替代完整桌面交互验收。 |
| Codex / Claude 启动 | 最终 `.251` 普通用户 UID 1100、HOME `/home/developer` 下，两 CLI 在真实 PTY 均存活 12 秒，识别到首次界面且未发现连接错误；两个真实桌面入口执行后，XFCE 终端和 CLI 子进程均存活 10 秒。 |

复验依据为本地 `outputs/qa/final-20261023/` 中的 `cleanup-result.json`、`lan-result.json`、`domain-result.json`、`cli-result.json`。该目录及现场截图由 Git 忽略，原始现场记录不随源码发布。上述结果是该时刻的证据，后续变更需复验受影响项。

个人登录与模型请求为 **NOT RUN**；首次界面、进程存活和 HTTP/TLS 连通不等于账号认证或模型调用成功。此组记录没有 Tailscale peer 双向访问证据，该项也不标为通过。完整鼠标键盘工作流、实际项目编辑和模型服务仍需相应验收。

CI 使用 `smoke.sh` 验证干净环境的桌面、权限与工具，再使用 `internal-storage.sh` 验证无挂载环境的认证、HOME、配置与主机密钥重启持久性，最后审计镜像的全部层。CLI 的外网首次启动验证单独执行，不放入断网的内部存储夹具。GHCR 发布与包可见性以对应 GitHub Actions 运行结果为准。

## 干净镜像构建历史快照：2026-10-23

以下是最终切换前的独立干净镜像验收记录，用于追溯构建验证。所列镜像、归档和临时目录已在后续清理中删除，不代表当前运行镜像或仍可访问的文件。

日期：2026-10-23，Asia/Taipei。目标：NAS SSD 上的 `linux/amd64`，独立临时测试容器；正式部署无业务挂载。

已确认 Docker Root `/volume1/@docker` 与 `/mnt/docker-ssd` 同属 `/dev/sdc1`（st_dev 2081）；构建、公开下载缓存和归档均在 SSD 的 `/mnt/docker-ssd/builds/ai-workstation/`。SSD 上先完成完整 smoke，随后只针对 CLI 启动器和桌面环境修复复验受影响项，复用同一工具安装层的有效 PASS。

- 镜像：`local/ai-workstation-clean:test`
- Image ID：`sha256:c7c483587354fe1771f2b6ea7ee38d1f3ab5fbe962a5b685e4b165786b28576d`
- 大小：3,792,304,142 bytes，约 3.79 GB。
- SSD 公开镜像归档：`/mnt/docker-ssd/builds/ai-workstation/artifacts/workstation/ai-workstation-clean-ssd-test.tar`
- 归档 SHA256：`3ff813098c007d0c879847ee233ac57304e459a913bb25abdacba107bba5485c`

### 历史验证结果

| 验证 | 结果与范围 |
| --- | --- |
| 干净构建 | 从官方 Ubuntu / Node 基础镜像、APT、固定公开下载和 npm lock 构建；基础镜像 blob/config/diffID 及工具 SHA256 校验通过。未使用业务容器快照。 |
| 源码对应 | 镜像内 33 个运行时、工具脚本、版本清单与桌面模板文件的 SHA256 与本地源码一致。 |
| 桌面 | X socket、XFCE session / desktop / panel 均启动；实际加载自定义 42px 面板。 |
| 权限 | dev UID/GID 1100；无 sudo、Docker socket、有效 capability；NoNewPrivs=1；root 默认锁定；用户 MCP 配置为 600。 |
| SSH / VNC | 真实 SSH 密码登录进入 dev；VNC 3.8 正确密码成功、错误密码拒绝；重启后再次通过认证。 |
| Chrome 沙箱 | 普通用户 user namespace 可用；Chrome 无禁用沙箱参数运行自包含 JavaScript 页面成功。 |
| 内部持久化 | 镜像无 `Config.Volumes`；实际容器 `Mounts=[]`。项目文件、Codex 用户配置、GitHub CLI 用户配置及 SSH 主机密钥重启后保留。ENV 方式 SSH/VNC 密码在重启前后通过真实认证。 |
| CLI 真实启动 | 新镜像中 Codex / Claude 经桌面包装在真实 PTY 持续存活 18 秒，分别显示登录和 theme 首次设置界面，无自然退出及连接错误；未执行个人登录或模型调用。 |
| 桌面代理环境 | 修复 `runuser -l` 清理运行时代理的问题；实际 `/proc` 检查普通用户 XFCE 收到测试代理值。桌面入口也可每次读取内部 `proxy.env`，不必重启桌面。8 项启动器回归通过。 |
| HOME 软链接 | dev 控制的 HOME 软链接不能修改 root 所有的 SSH 密钥目录或保护文件。 |
| 镜像审计 | manifest 声明的全部 16 层实际扫描通过，检查常见个人认证、私钥、浏览器资料、历史、烘焙密码和代理环境变量。审计为有界检测，结合构建输入白名单使用。 |
| 审计回归 | 18 项通过，覆盖已删除旧层中的私钥、密码、登录状态、缺层、坏层、截断层、OCI/gzip、流式大层及代理环境变量。 |
| 构建环境清理 | 工作站测试容器、测试卷和随机密码夹具已清理；网关构建完成后，本任务的临时公开下载转发（18746、18748）均已关闭。镜像与公开缓存保留。 |

固定版本实际检查：Node 24.22.1、Godot 4.7.2、Chrome 156.0.8078.47-1、VS Code 1.143.1-1792691907、Codex 0.164.0、Claude 2.1.309。Git 2.53.0、GitHub CLI 2.46.0 已安装并执行版本命令。

| 本地 MCP | 实际检查 |
| --- | --- |
| Context7 4.4.4 | stdio 握手及 2 项工具枚举通过；外部文档查询未运行。 |
| Playwright 0.0.83 | 25 项工具枚举及页面导航、JavaScript 求值通过。 |
| Chrome DevTools 1.12.0 | 32 项工具枚举及新建页面、JavaScript 求值通过。 |
| Godot MCP 0.1.1 | 14 项工具枚举及 Godot 版本调用通过。 |

完整命令在 [smoke.sh](tests/smoke.sh)、[认证测试](tests/auth-smoke.py)、[镜像审计](tests/audit-image.py) 和 [审计回归](tests/test-audit-image.py)。SSD 原始日志在 `workstation/test-results/20261023-ssd/`；迁移前历史证据保留在 `workstation/test-results/20261023-clean/`。NAS 构建目录为 `/mnt/docker-ssd/builds/ai-workstation/workstation`。新增 [无挂载验收](tests/internal-storage.sh)、[CLI PTY 验收](tests/cli-startup.py) 和 [启动器回归](tests/test-desktop-cli.py)。CLI PTY 验收仅在全新临时容器执行，输出只保留首次界面标记，无终端转录。

### 历史验收边界

- Mac 原生屏幕共享可视与鼠标键盘主流程：**NOT RUN**。当时 Codex 原生屏幕共享工具持续返回 `-10005 timeoutReached`；临时预览的 localhost 端口发布也遇到 NAS 缺少可用 `docker-proxy` 的宿主环境问题。该轮保留 NAS 全局配置并清理失败预览。SSH/VNC 协议和 PTY 验证通过不能替代 Mac 原生可视验收。
- GitHub MCP、GitHub CLI、Codex、Claude 个人授权及模型服务侧调用由用户完成；镜像没有个人令牌或登录状态。GitHub CLI 用户配置的持久化已测，个人账号登录尚未执行。
- Context7 外部查询、实际 Godot 项目与游戏性能、VS Code 项目编辑和扩展未验收。桌面采用 Mesa 软件渲染。
- 当时尚未完成最终地址切换与旧容器清理；这些项目的后续结果见上方“最终拓扑现场验收”。GHCR 的发布状态由对应 Actions 运行记录确认。

历史修复曾在原 `wb-ubuntu` 更新 Codex / Claude 桌面入口、普通账户启动包装及容器内部代理配置，当时使用 `.251:7890` 过渡代理。原容器已经删除，最终角色为 `.250` 网关和 `.251` 工作站。真实登录与模型调用继续保持未验收状态。
