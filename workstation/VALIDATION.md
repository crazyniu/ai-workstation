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
| `internal-storage.sh` | 镜像没有 `Config.Volumes`、容器 `Mounts=[]`、运行时密码认证、HOME/CLI 配置/GitHub CLI 设置/SSH 主机密钥在重启后保留、普通用户桌面代理环境，以及默认新加坡英文和内部文件修改地区后的重启验证。此夹具没有业务挂载。 |
| `audit-image.py` | 扫描 manifest 声明的全部镜像层，检查常见私人状态、认证文件、主机私钥、烘焙密码和代理环境。缺少或无法读取的层导致失败；检查结合构建允许清单使用。 |
| Python 回归测试 | 镜像审计、SSH/VNC 认证夹具、桌面 CLI 启动包装逻辑及地区配置校验/生成/优先级/失败边界。 |

`tests/cli-startup.py` 是独立的真实 PTY 首次启动检查，仅在无个人登录状态的临时容器中，以普通用户执行。它观察 Codex / Claude 首次界面与持续存活，检测连接错误，不提交任何登录或模型请求。该检查需要合适的外网出口，不放入断网的 `internal-storage.sh` 夹具。

## 2026-10-24 地区初始化与分开部署源码验证（未发布）

- PASS：工作站 Python 回归 39 项、部署入口保护回归 7 项，共 46 项；四份部署 Compose 的 `config --quiet` 及 Shell 语法检查通过。
- PASS：独立 gateway/workstation Compose 的服务设置与同机版本对应，移除了工作站对本地 gateway 的依赖，无业务挂载。
- PASS：在独立的 Linux amd64 临时容器内运行新地区初始化程序，实际生成默认 `en_SG.UTF-8`，登录用户得到新加坡英文与时区。内部 `region.json` 切换到 `en_US.UTF-8` / `America/New_York` 后，重启同一临时容器，配置与 HOME 测试数据保留，`Mounts=[]`。无效的时区文件被拒绝，原 locale 配置保持。测试容器已清理。
- NOT RUN：本次完整新镜像构建、完整桌面/SSH/VNC smoke 和镜像层审计；已为 `internal-storage.sh` 加入真实 XFCE 环境及地区变更重启断言，待新镜像运行。
- NOT RUN：两台独立宿主机之间的 LAN/VPN/代理真实部署验收。Compose 配置检查与单机临时容器验证不能替代跨设备连通性验收。

本节为当前源码的验证边界；不代表该功能已包含在下面记录的历史公开镜像或当前 `latest` 中。

## 2026-10-24 Claude 身份重置源码验证（未发布）

- 新增 `reset-claude-user` 镜像安装步骤、用户与 AI 使用说明及 CCBaga MIT 来源声明。命令默认预览，启动流程不调用清理。
- PASS：本地完整 Python 回归 57 项中 56 项通过，Linux `/proc` 进程检测 1 项因本机 macOS 跳过；随后在 Linux amd64 独立临时容器以普通用户运行新增的 11 项重置测试全部通过，包括真实 Claude 进程检测。
- PASS：临时容器中的 `/usr/local/bin/reset-claude-user` 实际预览保持身份字段，执行后删除身份字段并保留 MCP 配置和 MCP OAuth 凭据。新版 `smoke.sh` 已加入同一隔离 HOME 检查；真实部署没有执行账号清理。
- PASS：Shell 语法、文档本地链接及差异格式检查。重置测试使用临时 HOME，不读取真实用户凭据。
- NOT RUN：包含重置安装步骤的完整新镜像构建与全流程 smoke，由更新后的 PR CI 运行；不据临时容器的脚本验证宣称新镜像已发布。

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
