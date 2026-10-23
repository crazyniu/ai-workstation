# Contributing

欢迎修复问题、改进文档或提交功能建议。较大的功能请先用 Issue 说明使用场景、预期行为和影响范围。

## 本地开发

1. 从 `main` 创建分支，保持一个 Pull Request 聚焦一个完整问题。
2. 按 [README](README.md#开发与验证) 安装测试依赖并运行对应服务的检查。
3. 修改网关运行时或 Web 资源后运行 `python3 gateway/runtime/build-info.py`，提交生成的版本信息。
4. 在 PR 中说明行为变化、验证结果和未覆盖的环境；UI 变更附截图。

仓库不需要通用前端构建工具。网关 Web 使用原生 HTML、CSS 和 JavaScript；Python 后端测试使用 unittest。Linux 容器检查在 GitHub Actions 中执行。

## Favicon 资源

`gateway/web/favicon.svg` 是源文件。位图与多尺寸 ICO 已提交，常规镜像构建无需额外工具。调整图案后可在临时目录安装固定版本的 SVG 渲染器并重新生成：

```sh
npm install --prefix /tmp/gateway-icon-tools @resvg/resvg-js@2.6.2
NODE_PATH=/tmp/gateway-icon-tools/node_modules node gateway/scripts/build-favicon.cjs
python3 gateway/runtime/build-info.py
```

检查 16、32、48 像素下的清晰度，以及 SVG、PNG、ICO 与 Apple touch icon 的实际加载。站点 favicon 与用户添加链接的自动图标是两个独立功能。

## 容器与数据

- 公共镜像从仓库源码和锁定的上游文件构建，不从运行中的个人容器提交生成。
- 维持无业务挂载的默认部署方式，变更时验证 HOME、配置、SSH 身份和重启后的数据。
- 镜像重建测试使用可丢弃的测试容器；保留已有业务环境。
- 不提交 `.env`、订阅、私有节点、Tailscale 状态、账号令牌、SSH 私钥、运行日志或私有镜像。
- 新增第三方资源时记录来源、版本、校验值和许可，保留上游声明。

## 提交与审查

使用说明变化目的的提交信息。PR 至少包含变更说明与实际验证；不要将编译通过描述为桌面交互或远程网络验收通过。项目自有贡献按 [MIT License](LICENSE) 提交，第三方材料继续遵循原许可。
