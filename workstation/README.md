# AI 工作站镜像

此目录是统一仓库中的工作站构建上下文，网关、正式 Compose 和 GHCR 发布由仓库根目录统一管理。支持 `linux/amd64`。本次实际构建与测试范围见 [验证记录](VALIDATION.md)。

包含 Ubuntu、繁体中文及台北时区、XFCE 桌面、Mac 屏幕共享兼容的 VNC、SSH、Godot、Chrome、VS Code、Git、GitHub CLI、Codex CLI、Claude CLI，以及 Context7、Playwright、Chrome DevTools、Godot 和 GitHub 五项 MCP 配置。基础镜像固定到官方 amd64 manifest digest，应用版本及公开下载校验值见 `versions.env`；Ubuntu 系统软件随 APT 仓库更新。

```sh
docker build -t ai-workstation:test ./workstation
bash workstation/tests/smoke.sh ai-workstation:test
bash workstation/tests/internal-storage.sh ai-workstation:test
docker image save ai-workstation:test | python3 workstation/tests/audit-image.py
```

Docker 宿主机无法访问官方 registry 时，可在联网的 Mac/Linux 上使用 Python 3 与 curl 获取公开基础镜像，下载缓存和导出文件默认均在 `/tmp`，无需本机 Docker daemon：

```sh
python3 workstation/scripts/fetch-base-images.py
```

工具选择官方 Docker Hub 的 `linux/amd64` manifest，验证压缩 blob、config 和解压层 SHA256，生成 Docker load archive、`.sha256` 和 `.receipt.json`。校验保证下载和传输完整性；收据记录本次解析的 manifest digest。将导出目录传到构建宿主机后，在该目录执行：

```sh
sha256sum -c node-24.22.1-bookworm-slim-linux-amd64.tar.sha256
sha256sum -c ubuntu-26.04-linux-amd64.tar.sha256
docker load -i node-24.22.1-bookworm-slim-linux-amd64.tar
docker load -i ubuntu-26.04-linux-amd64.tar
docker tag node:24.22.1-bookworm-slim local/workstation-base-node:24.22.1-bookworm-slim
docker tag ubuntu:26.04 local/workstation-base-ubuntu:26.04
cd /你的路径/ai-workstation
docker build --pull=false \
  --build-arg NODE_BASE=local/workstation-base-node:24.22.1-bookworm-slim \
  --build-arg UBUNTU_BASE=local/workstation-base-ubuntu:26.04 \
  -t ai-workstation:test ./workstation
```

公开工具大文件也可事先下载到单独缓存目录，构建时附加 `--build-context tool-download-cache=/绝对路径/公开下载缓存`。文件名为 `codex-版本.tar.gz`、`claude-版本.zst`、`godot-版本.zip`；安装脚本仍按 `versions.env` 校验 SHA256，缺失文件从官方源下载。缓存以只读挂载供安装步骤使用，原始压缩包不保留在镜像层中。默认构建使用空缓存，无需准备该目录。

启动需要 `DEV_PASSWORD` 和 `VNC_PASSWORD`，也支持对应的 `_FILE` 变量读取容器内文件。`ROOT_PASSWORD` / `ROOT_PASSWORD_FILE` 可选；未提供时 root 密码登录锁定。VNC 使用兼容 Mac 屏幕共享的传统认证，密码为 1–8 个 ASCII 字节。运行时密码不写入镜像。独立 Compose 默认使用运行时环境变量设置密码；`_FILE` 也可读取容器内已准备的文件，无需外置业务挂载。

普通应用使用 `dev`，UID/GID 为 `1100`，HOME 为 `/home/dev`。HOME、项目、编辑器配置、CLI 登录和 `/etc/ssh/keys` 均保存在容器内部，默认部署没有业务绑定挂载或数据卷。容器正常重启保留这些内容；更换或重建容器前，先制作私有备份并在目标容器内恢复。首次初始化只拷贝缺失的桌面文件，MCP 配置合并保留已有设置。已有 `/home/developer` 的业务容器按协调迁移方案把所需数据复制入新容器，不直接覆盖为该干净镜像。


GitHub CLI 在普通用户会话中运行 `gh auth login`，登录文件保存在容器内部的 HOME，正常重启保留；镜像不携带个人令牌。Codex 和 Claude 分别运行 `codex`、`claude` 完成用户自己的登录。GitHub MCP 已配置远程地址，仍需个人授权；其余四项 MCP 可在无模型账号时执行握手测试。

Chrome 使用自身沙箱。启动时须使用 `security/seccomp-chrome.json`、`no-new-privileges:true` 和至少 `512m` 共享内存，参照目录中的独立 `compose.yaml` 示例。桌面会话使用专门限定范围的 bwrap 兼容包装程序。

Mac 可以通过 SSH 转发访问示例中仅绑定本机的 VNC：`ssh -L 5901:127.0.0.1:5901 -p 2222 dev@宿主机`，随后打开 `vnc://127.0.0.1:5901`。正式局域网地址由根 Compose 设置。

网络出口由容器外的网关配置决定，镜像不内置代理地址。台北时区及中文区域配置不会改变公网出口，也不会使容器变成物理电脑。

需要显式代理时，可在运行时传入 `HTTP_PROXY`、`HTTPS_PROXY` 和 `NO_PROXY`，桌面会话会保留这些环境变量。桌面 Codex / Claude 启动器还会在每次启动时读取容器内部可选的 `/etc/workstation/proxy.env`；该文件仅支持上述代理变量及 `ALL_PROXY` 和对应小写形式，进程已有同名环境变量优先。文件按 `KEY=value` 存放，作为数据读取，不执行 shell。请在私有部署时配置实际出口，不把个人代理凭据提交到镜像或仓库。

两个 AI CLI 桌面入口会按当前普通账户选择 HOME 和 Projects，失败后保留终端错误，退出码及代理是否存在记录到 `~/.local/state/workstation/launcher-errors.jsonl`。该日志不记录 CLI 输出、参数、环境变量值或对话。已有 HOME 的旧桌面文件保留；升级时按需更新这两个启动入口。

镜像完全由公开安装源和静态模板构建，不从现有业务容器提交快照，不包含浏览器资料、模型认证、GitHub 登录、SSH 私钥或现有项目数据。`tests/audit-image.py` 检查每一镜像层中的常见私有资料，`tests/smoke.sh` 在独立临时容器中验证桌面、CLI、MCP、Chrome 沙箱、持久化重启及 HOME 软链接隔离。
