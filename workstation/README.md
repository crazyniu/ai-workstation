# AI 工作站镜像

此目录是统一仓库中的工作站构建上下文，网关、正式 Compose 和 GHCR 发布由仓库根目录统一管理。支持 `linux/amd64`。可复现的验证步骤及发布记录见 [验证记录](VALIDATION.md)。

包含 Ubuntu、新加坡英文及新加坡时区、XFCE 桌面、Mac 屏幕共享兼容的 VNC、SSH、Godot、Chrome、VS Code、Python 3、Node.js、Git、GitHub CLI、Codex CLI、Claude CLI，以及 Context7、Playwright、Chrome DevTools、Godot 和 GitHub 五项 MCP 配置。国家、语言和时区可在初始化时配置。基础镜像固定到官方 amd64 manifest digest，应用版本及公开下载校验值见 [`versions.env`](versions.env)；Ubuntu 系统软件随 APT 仓库更新。

## 已安装的软件

| 类别 | 软件与版本 | 用途 |
| --- | --- | --- |
| 基础系统 | Ubuntu `26.04` | Linux amd64；默认新加坡英文与 `Asia/Singapore`，可配置 |
| 桌面 | XFCE、XFWM、XFCE Panel / Terminal、Thunar | 图形桌面、终端与文件管理 |
| 远程连接 | TigerVNC、OpenSSH Server | VNC 桌面与 SSH 登录 |
| 浏览器 | Google Chrome `156.0.8078.47-1` | 桌面浏览器和浏览器 MCP 运行环境 |
| 编辑器 | Visual Studio Code `1.143.1-1792691907` | 项目编辑与开发 |
| 游戏开发 | Godot `4.7.2` | 编辑器、命令行与 Godot MCP |
| AI CLI | Codex `0.164.0`、Claude Code `2.1.309` | 终端及桌面入口，使用个人模型账号 |
| Python | Python 3（Ubuntu 软件包，`3.14` 系列） | 脚本、工具与系统服务运行 |
| JavaScript 开发 | Node.js `24.22.1`、npm / npx | JavaScript 开发与本地 MCP 服务 |
| 开发工具 | Git、GitHub CLI、GCC、curl | 版本管理、GitHub、C 编译与下载 |
| 系统服务 | Supervisor、D-Bus、Ubuntu 系统 Python `3.14` | 会话、SSH/VNC 和工作站启动服务 |
| 桌面资源 | Arc、Papirus、Inter、Noto CJK、DejaVu、Mesa | 主题、图标、中西文字体与软件图形渲染 |

Chrome、VS Code、AI CLI、Godot 和 Node.js 的固定版本以 [`versions.env`](versions.env) 及 [`Dockerfile`](Dockerfile) 为准；Python 和其他 Ubuntu 软件包按构建时的软件源安装，补丁版本随系统更新。

### MCP 工具

以下默认配置同时写入 Codex 与 Claude 的配置文件，已有同名用户设置保留。

| 工具 | 类型 / 固定版本 | 用途 |
| --- | --- | --- |
| Context7 | 本地 `@upstash/context7-mcp` `4.4.4` | 查询开发文档与示例 |
| Playwright | 本地 `@playwright/mcp` `0.0.83` | 使用容器内 Chrome 进行浏览器操作 |
| Chrome DevTools | 本地 `chrome-devtools-mcp` `1.12.0` | Chrome 调试与浏览器检查 |
| Godot | 本地 `@coding-solo/godot-mcp` `0.1.1` | 调用容器内 Godot 工具 |
| GitHub | 远程 `https://api.githubcopilot.com/mcp/` | GitHub 操作，需个人授权 |

本地 MCP 通过 `/usr/local/bin/workstation-mcp` 启动，依赖锁定在 [`mcp/package-lock.json`](mcp/package-lock.json)，其中 MCP SDK 为 `1.32.1`。配置生成方式见 [`scripts/configure-mcp.py`](scripts/configure-mcp.py)。

### Python 环境

工作站使用 Ubuntu 提供的 Python `3.14` 系列，解释器位于 `/usr/bin/python3`。在桌面终端或 SSH 会话中通过 `python3` 运行脚本，具体补丁版本可直接查询：

```sh
python3 --version
```

## 构建与运行

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

普通应用使用 `dev`，UID/GID 为 `1100`，HOME 为 `/home/dev`。HOME、项目、编辑器配置、CLI 登录和 `/etc/ssh/keys` 均保存在容器内部，默认部署没有业务绑定挂载或数据卷。容器正常重启保留这些内容；更换或重建容器前，先制作私有备份并在目标容器内恢复。首次初始化只拷贝缺失的桌面文件，MCP 配置合并保留已有设置。迁移其他镜像时，应先核对原用户的 UID/GID、HOME 和启动方式，再选择应用状态迁移或完整私有快照恢复。


GitHub CLI 在普通用户会话中运行 `gh auth login`，登录文件保存在容器内部的 HOME，正常重启保留；镜像不携带个人令牌。Codex 和 Claude 分别运行 `codex`、`claude` 完成用户自己的登录。GitHub MCP 已配置远程地址，仍需个人授权；其余四项 MCP 可在无模型账号时执行握手测试。

Chrome 使用自身沙箱。启动时须使用 `security/seccomp-chrome.json`、`no-new-privileges:true` 和至少 `512m` 共享内存，参照目录中的独立 `compose.yaml` 示例。桌面会话使用专门限定范围的 bwrap 兼容包装程序。

Mac 可以通过 SSH 转发访问示例中仅绑定本机的 VNC：`ssh -L 5901:127.0.0.1:5901 -p 2222 dev@宿主机`，随后打开 `vnc://127.0.0.1:5901`。正式局域网地址由根 Compose 设置。

### 国家、语言与分开部署（供安装 AI 使用）

在私有 `.env` 或 `docker run -e` 中设置 `WORKSTATION_COUNTRY=SG`、`WORKSTATION_LANGUAGE=en`、`WORKSTATION_TIMEZONE=Asia/Singapore`。默认生成 `en_SG.UTF-8`，同步用于 SSH 登录和 XFCE。其他示例为 `TW / zh / Asia/Taipei`、`US / en / America/New_York`；组合须是镜像 glibc 支持的 locale。无效输入会中止初始化。不要通过额外的 `LANG` / `TZ` 覆盖这套参数。

已有容器可使用内部 `/etc/workstation/region.json` 覆盖部分或全部参数，再重启同一容器：`{"country":"SG","language":"en","timezone":"Asia/Singapore"}`。内部文件优先于运行时环境变量；不会清理 HOME、MCP 或用户身份。此方式要求镜像实际包含 `runtime/region.py` 对应的初始化入口；不能把本次源码当作已经发布的新镜像。完整操作、参数优先级及真实登录验收见 [AI-INSTALL 第 2.1 节](../AI-INSTALL.md#21-工作站国家语言和时区初始化)。

工作站 251 可在宿主机 A、网关 250 在宿主机 B。同一二层 LAN 使用根目录 `./deploy.sh gateway`（B）与 `./deploy.sh workstation`（A），各自设置本机网卡；不同网段使用 `./deploy.sh workstation-bridge`（A），将 `WORKSTATION_HTTP_PROXY` / `WORKSTATION_HTTPS_PROXY` 指向已验证可达的网关私有代理端点。bridge 模式不使用远端 250 作为本地 IPAM 默认网关，也不依赖 B 的 Docker bridge 或 Compose 服务名。拓扑、端口与部署顺序见 [AI 安装指南](../AI-INSTALL.md#0-先确定角色宿主机和网络拓扑)。

网络出口由容器外的网关配置决定，镜像不内置代理地址。地区语言与时区设置独立于公网出口。

需要显式代理时，可在运行时传入 `HTTP_PROXY`、`HTTPS_PROXY` 和 `NO_PROXY`，桌面会话会保留这些环境变量。桌面 Codex / Claude 启动器还会在每次启动时读取容器内部可选的 `/etc/workstation/proxy.env`；该文件仅支持上述代理变量及 `ALL_PROXY` 和对应小写形式，进程已有同名环境变量优先。文件按 `KEY=value` 存放，作为数据读取，不执行 shell。请在私有部署时配置实际出口，不把个人代理凭据提交到镜像或仓库。

两个 AI CLI 桌面入口会按当前普通账户选择 HOME 和 Projects，失败后保留终端错误，退出码及代理是否存在记录到 `~/.local/state/workstation/launcher-errors.jsonl`。该日志不记录 CLI 输出、参数、环境变量值或对话。已有 HOME 的旧桌面文件保留；升级时按需更新这两个启动入口。

镜像完全由公开安装源和静态模板构建，不从现有业务容器提交快照，不包含浏览器资料、模型认证、GitHub 登录、SSH 私钥或现有项目数据。`tests/audit-image.py` 检查每一镜像层中的常见私有资料，`tests/smoke.sh` 在独立临时容器中验证桌面、CLI、MCP、Chrome 沙箱、持久化重启及 HOME 软链接隔离。


## 数据、备份与恢复

在仓库根目录操作，确保正在使用原部署的 `.env`、Compose 项目名和 Docker context。`deploy.sh` 只用于首次创建，已有容器会被它拒绝；日常启停用 `docker compose start` / `stop` / `restart`。两个方案均先停止工作站，备份存放在仓库外的私有目录，完成后可以重新启动原容器。

下列命令按同机的根 Compose 编写。独立部署时，在工作站宿主机 A 执行，并为每条 `docker compose` 命令添加 `--env-file .env -f compose.workstation.yaml`（LAN）或 `--env-file .env -f workstation/compose.yaml`（bridge），保持原项目身份。

### 完整私有快照与原版本恢复

完整回退以私有镜像快照最直接：它保留容器写入层中的 HOME、项目、SSH 主机密钥、`/etc/workstation/proxy.env`、`/etc/workstation/region.json`、账号库和额外安装的软件，文件 UID/GID 与权限随镜像保留。外部挂载和运行中内存不在镜像快照内；本项目默认 Compose 没有业务挂载。Docker 网络、端口、安全参数和运行时环境属于容器定义，应同时保存。此方案恢复原软件版本，不等同于升级到新的公开镜像。

```sh
set -eu
umask 077
container=$(docker compose ps --all --quiet workstation)
test -n "$container"
workstation_stamp=$(date +%Y%m%d-%H%M%S)
workstation_backup="${HOME}/ai-workstation-private/${workstation_stamp}"
private_image="local/ai-workstation-private:${workstation_stamp}"
mkdir -p "$workstation_backup/workstation/security"
docker compose stop workstation
docker inspect "$container" > "$workstation_backup/container-inspect.json"
cp .env "$workstation_backup/runtime.env"
cp compose.yaml "$workstation_backup/compose.yaml"
cp workstation/security/seccomp-chrome.json "$workstation_backup/workstation/security/"
docker commit "$container" "$private_image"
docker image save -o "$workstation_backup/image.tar" "$private_image"
printf '%s\n' "$private_image" > "$workstation_backup/image-tag.txt"
(cd "$workstation_backup" && sha256sum image.tar > image.tar.sha256)
# 仅备份时，继续使用原容器：
docker compose start workstation
```

这些文件包含个人数据和运行时凭据，不上传到 Git、GHCR 或公开附件。还原前校验归档，将备份中的 Compose、安全配置及环境设置与目标主机对齐；使用相同项目名替换工作站，保证旧实例已停止。设置 `workstation_backup` 为实际备份目录，并在根 `.env` 中将 `WORKSTATION_IMAGE` 改为 `image-tag.txt` 记录的本地镜像标签：

```sh
set -eu
(cd "$workstation_backup" && sha256sum -c image.tar.sha256)
docker image load -i "$workstation_backup/image.tar"
# 确认 .env 中已选择加载的私有镜像及原运行时账号设置。
docker compose config --quiet
docker compose up --no-start --no-deps --force-recreate workstation
docker compose start workstation
docker compose ps workstation
```

### 应用状态迁入新的公开镜像

此方案适用于本项目的 `dev` 用户（UID/GID `1100`，HOME `/home/dev`）。它迁移应用数据与 SSH 服务器身份；它不复制 `/etc/passwd`、系统密码、额外系统软件或所有容器配置。登录密码仍由 `.env` 的运行时变量初始化。若原容器采用其他 HOME 或账号结构，先完成路径和账号映射，或使用完整私有快照恢复原环境。

在停止的原容器上导出 tar 流，避免在 macOS 或不支持 Unix 权限的文件系统中展开 HOME：

```sh
set -eu
umask 077
container=$(docker compose ps --all --quiet workstation)
test -n "$container"
workstation_backup="${HOME}/ai-workstation-private/state-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$workstation_backup"
docker compose stop workstation
docker cp -a "$container":/home/dev - > "$workstation_backup/home-dev.tar"
docker cp -a "$container":/etc/ssh/keys - > "$workstation_backup/ssh-keys.tar"
docker inspect "$container" > "$workstation_backup/container-inspect.json"
cp .env "$workstation_backup/runtime.env"
```

若使用了容器内部的 `/etc/workstation/proxy.env`，再单独导出它；未配置该文件时跳过：

```sh
set -eu
docker cp -a "$container":/etc/workstation/proxy.env - > "$workstation_backup/proxy-env.tar"
```

若使用了容器内部的地区覆盖 `/etc/workstation/region.json`，同样单独导出；未配置时跳过。该文件的优先级高于新容器的环境变量，迁移时应核对其国家、语言和时区仍符合目标要求：

```sh
set -eu
docker cp -a "$container":/etc/workstation/region.json - > "$workstation_backup/region-json.tar"
```

确认归档完整后，在 `.env` 中选择新的公开镜像及运行时密码。创建新容器但暂不启动，将 tar 流直接放回相同父目录：

```bash
set -euo pipefail
tar -tf "$workstation_backup/home-dev.tar" > /dev/null
tar -tf "$workstation_backup/ssh-keys.tar" > /dev/null
if [ -f "$workstation_backup/proxy-env.tar" ]; then
  tar -tf "$workstation_backup/proxy-env.tar" > /dev/null
fi
if [ -f "$workstation_backup/region-json.tar" ]; then
  tar -tf "$workstation_backup/region-json.tar" > /dev/null
fi
docker compose pull workstation
docker compose up --no-start --no-deps --force-recreate workstation
new_container=$(docker compose ps --all --quiet workstation)
test -n "$new_container"
docker cp - "$new_container":/home < "$workstation_backup/home-dev.tar"
docker cp - "$new_container":/etc/ssh < "$workstation_backup/ssh-keys.tar"
if [ -f "$workstation_backup/proxy-env.tar" ]; then
  docker cp - "$new_container":/etc/workstation < "$workstation_backup/proxy-env.tar"
fi
if [ -f "$workstation_backup/region-json.tar" ]; then
  docker cp - "$new_container":/etc/workstation < "$workstation_backup/region-json.tar"
fi
# tar 流保留数值 UID/GID 与权限；恢复使用归档原值，不启用 cp -a 的目标用户映射。
# 启动前核对 HOME 根目录、SSH keys 及代理文件的属主和权限与原归档一致：
docker cp -a "$new_container":/home/dev - | tar --numeric-owner -tvf -
docker cp -a "$new_container":/etc/ssh/keys - | tar --numeric-owner -tvf -
docker compose start workstation
docker compose ps workstation
```

确认项目文件、CLI 配置、SSH/VNC 登录和重启持久性后，再按自己的保留策略清理私有备份。账号授权能否跨软件版本继续使用由各应用决定；文件恢复成功不代表模型认证或外部服务调用已经通过。
