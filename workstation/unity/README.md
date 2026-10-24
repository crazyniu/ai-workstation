# Unity Personal 与 Claude MCP

工作站使用 Unity Personal 免费许可证。Unity Editor、Hub 和账号许可遵循 Unity 自己的条款；本仓库不包含激活文件、Unity 账号或付费服务凭据。

| 组件 | 固定版本 | 来源 |
| --- | --- | --- |
| Unity Editor | 6.3 LTS / `6000.3.27f1` | [Unity 官方下载](https://unity.com/releases/editor/whats-new/6000.3.27f1) |
| Unity Hub | `3.22.4` | [Unity Linux 安装说明](https://docs.unity.com/en-us/hub/install-hub-linux) |
| MCP for Unity | `10.3.0`，提交 `aa5fc638d623f56178d50329d9ad8c541a57fe66` | [CoplayDev/unity-mcp](https://github.com/CoplayDev/unity-mcp/tree/v10.3.0)，MIT |
| uv / uvx | `0.13.5` | [astral-sh/uv](https://github.com/astral-sh/uv/releases/tag/0.13.5)，MIT / Apache-2.0 |

下载 URL 和 SHA256 见 [versions.env](versions.env)，Unity MCP 全部 Python 依赖及校验值见 [requirements.lock](requirements.lock)。使用系统 Python 3.14 创建独立环境，不更改系统 Python 包；桥接包和服务端保持同一上游版本。

## 安装编辑器

公共镜像默认安装 Unity MCP 和桥接包，编辑器及 Hub 单独下载。在实际工作站容器中以 root 运行：

```sh
bash /opt/workstation/scripts/install-unity.sh
```

编辑器安装到 `/opt/unity/6000.3.27f1`，入口为 `unity-editor`；Hub 入口为 `unityhub`。固定版本已安装时保留该目录。脚本保留现有 HOME、项目、模型登录及 MCP 设置，不修改容器定义。

已有旧版容器若没有 `/opt/workstation`，先将本目录与 `scripts/install-unity-mcp.sh`、`scripts/install-unity.sh`、`scripts/unity-mcp`、`scripts/configure-mcp.py` 按相同相对结构复制到容器内 `/opt/workstation`，再执行：

```sh
bash /opt/workstation/scripts/install-unity-mcp.sh
bash /opt/workstation/scripts/install-unity.sh
runuser -l dev -c 'python3 /opt/workstation/scripts/configure-mcp.py --only unity'
```

`--only unity` 为 Claude 和 Codex 追加 Unity MCP；已有同名配置和其他字段保留。通过 `getent passwd dev` 确认实际 HOME，旧部署可能为 `/home/developer`，新镜像为 `/home/dev`，应使用登录用户的真实 HOME。

## 免费许可证与项目连接

1. 以普通用户打开 Unity Hub，登录自己的 Unity 账号，在许可证设置中选择 Unity Personal，按实际资格和条款完成激活。
2. 在 Hub 的 Installs 中定位已有编辑器 `/opt/unity/6000.3.27f1/Editor/Unity`，创建或打开项目。
3. 在 Unity 的 Window → Package Manager → `+` → Install package from disk 中选择 `/opt/workstation/unity/MCPForUnity/package.json`。
4. 打开 Window → MCP for Unity，选择 **stdio** 传输并启动 Unity 侧连接；Claude/Codex 已配置本机 `/usr/local/bin/unity-mcp`，每个客户端按需启动独立服务。
5. 在 251 项目目录执行 `claude mcp get unity` 检查连接；需要重启已打开的 Claude 会话才能读取新配置。

MCP 使用开源本地服务；图像、音频或模型生成等上游可选工具可能需要额外服务，本次安装和测试不调用这些工具，也不配置相关付费账号。

## 验证

```sh
unity-editor -version
uv --version
claude mcp get unity
```

MCP 握手和工具枚举可在编辑器未激活时通过；只有实际连接项目后完成场景读取、创建对象和测试，才能证明编辑器控制链路可用。首次激活需要用户账号操作，不能由服务器握手结果代替。

Unity 6.3 官方列出的 Linux 环境为 Ubuntu 22.04/24.04 与对应显卡驱动。本工作站为 Ubuntu 26.04、XFCE/VNC，使用 Mesa 软件 OpenGL；启动成功的验证范围及未覆盖的项目交互见 [验证记录](../VALIDATION.md)。在 VNC 中可使用 `unity-editor -force-glcore`，默认不开放额外的外部 MCP 端口。

重启同一容器保留安装和身份；重建或删除容器会丢失内部状态。可选安装的 Unity Editor/Hub 不包含在基础公共镜像里，升级前按工作站说明备份私有状态并记录额外安装内容。
