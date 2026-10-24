# Mac Orca 与 Linux 远程执行

Mac 运行 Orca 桌面端，Linux 工作站负责项目文件、智能体、构建和测试。Orca managed server 由 Mac 的 SSH 连接部署和管理；它是用户 HOME 内的运行时，独立于本仓库的公共镜像。本文基于 Orca `1.4.239` 的实际检查；其他版本以本机 CLI 帮助和[官方 SSH 说明](https://www.onorca.dev/docs/ssh)为准。

## 先检查现有环境

连接工作站现有 `dev` 用户，查询账号数据库和实际登录环境：

```sh
id
getent passwd dev
printf 'HOME=%s\n' "$HOME"
ps -p 1 -o pid,comm,args
command -v git codex claude orca
git --version
codex --version
claude --version
```

本仓库新镜像默认 HOME 为 `/home/dev`；迁移过的环境可能使用 `/home/developer` 等路径。后续操作使用查询得到的 HOME，保留其用户 ID、项目、登录和配置。

检查 SSH 服务、SFTP、PTY 和 TCP forwarding；Orca 通过 SSH 转发访问远程回环地址上的服务。已有容器从其实际宿主机核对容器身份、挂载、启动策略和 Supervisor 配置。保持现有代理、路由和端口范围。

检查已有运行时及 CLI：

```sh
ls -ld "$HOME/.orca" "$HOME/.orca-remote" 2>/dev/null
test ! -x "$HOME/.orca/cli/bin/orca" || "$HOME/.orca/cli/bin/orca" status --json
```

结合进程的实际参数、属主和监听地址确认 managed server；存在且正常时直接复用。外部 SSH Shell 可能尚未把 Orca CLI 加入 PATH，而 Orca 新建的远程终端已经可以使用它。先打开新终端确认；确需普通 SSH 会话使用时，可将已存在的 `$HOME/.orca/cli/bin/orca` 链接到该用户已有 PATH 目录，先检查目标位置并保留已有命令。

Git、Codex 或 Claude 缺失时，按工作站已有安装方式和官方来源补齐。安装与验收保留原认证文件，登录状态另行核实。

## 在 Mac 完成 SSH 连接

1. 打开 Orca **设置 → SSH 主机**。先查看已有主机项的实际用户、地址和端口；显示名称可能沿用旧用户名。
2. 已有 dev 主机项时选择连接。确实缺少主机项时，添加工作站地址、用户 `dev`、实际 SSH 端口及所用身份文件，测试后保存。需要密码、密钥口令或主机指纹确认时，在 Mac 完成对应提示。
3. 首次连接会自动部署 Orca 自带的固定版本运行时，已有兼容版本则复用。连接失败时按提示处理下载、权限或 SSH forwarding 问题，并从设置中的服务器管理入口检查版本和状态。
4. 添加或选择远程项目，使用服务器上的真实绝对路径。打开一个新的远程终端，确认 `id`、`$HOME` 和 `pwd` 均属于目标工作站。

Linux 端无需安装 Orca 桌面 GUI。managed server 保持私有回环监听，Mac 经 SSH 访问，无需映射或开放公网 Orca 端口。

## CLI、编排技能与登录

在 dev 的远程终端运行：

```sh
orca status --json
orca skills install --help
orca skills install --skill orca-cli --skill orchestration --agent claude,codex --json
orca skills installed --json
orca orchestration run-list --limit 1 --json
codex login status
claude auth status
```

`1.4.239` 使用随 CLI 打包的技能，写入 `~/.agents/skills`，并按目标智能体建立入口。安装结果应确认两个技能可被目标智能体读取；已有自定义同名技能先核对安装报告，保留用户修改。

远程 CLI 的默认控制范围受主机设置限制。需要远程智能体创建工作树、终端或调度任务时，在 Mac **设置 → SSH 主机 → 编辑目标 → 高级连接**检查“允许此主机的 orca CLI 控制 Orca”，按该主机的授权范围启用。[官方控制范围说明](https://www.onorca.dev/docs/ssh#the-orca-cli-on-an-ssh-host)

缺少 Claude 登录时，在 Mac Orca 打开的 dev 远程终端执行 `orca account add --agent claude`，由用户完成首次设置和浏览器授权。Codex 可通过 `orca account add --agent codex` 完成远程账号授权。认证属于执行主机；安装 CLI、启动首次界面和 Mac 本机已有登录分别核验。

## 验收完整开发路径

在独立测试目录执行以下检查，记录真实结果：

| 检查 | 通过依据 |
| --- | --- |
| SSH 与远程终端 | 从 Mac Orca 新建终端，验证 dev、实际 HOME、项目目录及命令输出 |
| 项目文件访问 | 在 Mac Orca 编辑器打开远程测试文件，检查内容；测试写入后从远程 Shell 读回 |
| 智能体启动与调用 | 通过 Orca 启动新智能体，让它读取测试输入、写出结果、运行校验并返回回复 |
| 编排技能 | 目标智能体可读取 `orca-cli`、`orchestration`，编排 CLI 的只读查询成功；需要多智能体编排时另测任务分发和结果回收 |
| 断线与恢复 | SSH 重新连接后复查运行时、终端及项目；安排重启时另验同容器重启后的恢复 |
| 数据与边界 | 保留原身份、代理和项目，核对服务数量、属主和监听范围，结束本次测试进程 |

服务 ready 只证明运行时可达。首次界面只证明 CLI 可以启动；模型调用、文件写回、编排任务及重启恢复按各自的实际证据报告。未登录、无法使用的客户端或未安排的宿主重启记为 **需用户登录** 或 **NOT RUN**。

## 重启与日常管理

沿用现有容器及服务管理方式。Docker 宿主的启动依赖、实际容器的 restart policy 和容器内部的 SSH 服务需分别核对。Mac Orca 重连时管理远程运行时的启动与恢复，避免为同一运行时额外添加 Supervisor、systemd、cron 或 Shell 后台启动入口。

网络断开或关闭 Mac 桌面端时，managed server 可保留远程会话；Linux 容器或宿主重启会结束其中的进程，重连后检查 Orca 的会话恢复或继续提示。同容器重启保留内部 HOME；删除或重建容器前，按[工作站数据恢复说明](../workstation/README.md#数据备份与恢复)处理 Orca 配置、项目和身份。

实际部署地址、主机标签、个人账号状态及原始日志保存在私有验收记录中。公共文档记录操作方法；本仓库镜像 CI 不代表某台服务器的 Orca 全流程已经通过。
