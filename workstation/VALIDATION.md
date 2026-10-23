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
| `internal-storage.sh` | 镜像没有 `Config.Volumes`、容器 `Mounts=[]`、运行时密码认证、HOME/CLI 配置/GitHub CLI 设置/SSH 主机密钥在重启后保留，以及普通用户桌面代理环境。此夹具没有业务挂载。 |
| `audit-image.py` | 扫描 manifest 声明的全部镜像层，检查常见私人状态、认证文件、主机私钥、烘焙密码和代理环境。缺少或无法读取的层导致失败；检查结合构建允许清单使用。 |
| Python 回归测试 | 镜像审计、SSH/VNC 认证夹具及桌面 CLI 启动包装逻辑。 |

`tests/cli-startup.py` 是独立的真实 PTY 首次启动检查，仅在无个人登录状态的临时容器中，以普通用户执行。它观察 Codex / Claude 首次界面与持续存活，检测连接错误，不提交任何登录或模型请求。该检查需要合适的外网出口，不放入断网的 `internal-storage.sh` 夹具。

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
