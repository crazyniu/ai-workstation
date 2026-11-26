# Contributing

欢迎修复问题、改进文档或提交功能建议。较大的功能请先用 Issue 说明使用场景、预期行为和影响范围。

Issue 和 PR 可以用中文或英文（English is welcome too）。参与即表示同意遵守[行为准则](CODE_OF_CONDUCT.md)；安全问题按 [SECURITY.md](SECURITY.md) 私密报告。

Niu Gateway（网关 Web）界面使用简体中文。新增的界面文字保持简体中文；修改 README 的用户可见内容时，同步更新 [README.en.md](README.en.md) 的对应段落。

## 本地开发

1. 从 `main` 创建分支，保持一个 Pull Request 聚焦一个完整问题。
2. 按 [README](README.md#开发与验证) 安装测试依赖并运行对应服务的检查。
3. 修改网关运行时或 Web 资源后运行 `python3 gateway/runtime/build-info.py`，提交生成的版本信息。
4. 在 PR 中说明行为变化、验证结果和未覆盖的环境；UI 变更附截图。

仓库不需要通用前端构建工具。Niu Gateway 使用原生 HTML、CSS 和 JavaScript；Python 后端测试使用 unittest。Linux 容器检查在 GitHub Actions 中执行。

## 图标资源

网关应用图标、favicon、Apple touch icon 和设置侧栏图标由 `gateway/scripts/build-icons.py` 生成。应用图标的原画在 `gateway/art/icons/`（1024 × 1024 方形，不进入镜像）；脚本把它们裁成 macOS 连续圆角方形，加上玻璃边和阴影，输出到 `gateway/web/icons/apps/`。设置图标使用 `web/index.html` 里的符号。修改原画或配色后运行：

```sh
python3 -m pip install Pillow
python3 gateway/scripts/build-icons.py
python3 gateway/runtime/build-info.py
```

检查 16、32、48 像素下的清晰度，以及 PNG、ICO、SVG 与 Apple touch icon 的实际加载。链接图标（`gateway/web/icons/*.svg`）是手写 SVG，来源见 `gateway/web/icons/PROVENANCE.md`。站点 favicon 与用户添加链接的自动图标是两个独立功能。

## 容器与数据

- 公共镜像从仓库源码和锁定的上游文件构建，不从运行中的个人容器提交生成。
- 维持无业务挂载的默认部署方式，变更时验证 HOME、配置、SSH 身份和重启后的数据。
- 镜像重建测试使用可丢弃的测试容器；保留已有业务环境。
- 不提交 `.env`、订阅、私有节点、Tailscale 状态、账号令牌、SSH 私钥、运行日志或私有镜像。
- 新增第三方资源时记录来源、版本、校验值和许可，保留上游声明。

## 提交与审查

使用说明变化目的的提交信息。PR 至少包含变更说明与实际验证；不要将编译通过描述为桌面交互或远程网络验收通过。项目自有贡献按 [MIT License](LICENSE) 提交，第三方材料继续遵循原许可。

## 默认分支保护

`main` 通过 GitHub Ruleset 保护：变更经 PR 合并，要求 `Required checks` 由 GitHub Actions 成功报告、分支与目标分支保持最新、所有审查讨论已解决，并保持线性历史；禁止强推和删除，管理员不设绕过。

`scripts/ci-changes.py` 按改动决定要跑的任务，所有 PR 都报告同一个必过检查 `Required checks`：

- **纯文档**：只做变更范围检查。
- **代码**：运行快速检查（网关、仓库和工作站的单元测试，以及网关 JavaScript 语法），通常一两分钟。
- **镜像构建定义**：改动网关的 `Dockerfile`、组件锁定文件、`scripts/`、`runtime/` 或冒烟测试脚本，或改动工作站目录中单元测试以外的文件时，只构建对应镜像的 amd64 版本并运行启动验收、镜像审计和原生安装检查。PowerShell 入口、Compose 文件或 AI 安装检查变化时运行 Windows 部署检查。
- **完整验证**：给 PR 加 `full-ci` 标签，或手动运行工作流并勾选 `full`，会构建并验证所有镜像和架构。修改 CI 本身（`scripts/ci-changes.py` 或 `images.yml`）时自动完整验证。

合并到 `main` 后，只重新构建自上次成功发布以来源码有变化的镜像，覆盖全部架构并验证通过后发布；未变化的镜像把上次发布的版本标记为本次提交的 `sha-<提交号>` 和 `latest`。发布失败时 `latest` 保持上一个通过验证的版本。其他架构的问题可能在合并后才发现，需要提前确认时使用 `full-ci`。测试失败、取消或未正常报告都会阻止通过。合并使用 squash 或 rebase。

Niu Gateway 的网页和 API 另外通过 GitHub Releases 发布：维护者在已合并的 `main` 提交上推送 `gateway-web-vX.Y.Z` 标签，[发布工作流](.github/workflows/gateway-web-release.yml) 打包 `gateway-web.tar.gz` 并设为最新版本，网关的“服务升级”据此在线更新。版本号每次加 0.01，例如 v1.4.0 → v1.4.1。

仓库已开启 GitHub 自动合并。完成授权开发并创建非草稿 PR 后，立即执行 `gh pr merge <编号> --auto --squash --match-head-commit <当前提交>`，由 GitHub 在必过检查及其他保护条件满足后合并。依赖 PR 按顺序合并，后续分支移到最新 `main` 再验证；提交者持续处理 CI 失败并确认最终合并状态。

仓库当前只有一名维护者，审批票数为 0，保留 PR 和 CI 门槛；加入其他维护者后可提高审批票数并启用最新推送需他人批准。实际服务器规则见 [Protect default branch](https://github.com/crazyniu/ai-workstation/rules/25768868)，版本化配置为 [main.json](.github/rulesets/main.json)；更新规则时同时核对工作流的检查名和 GitHub Actions 来源。
