---
name: "Gateway Desktop"
description: "macOS 27 视觉语言的网关桌面：菜单栏、Dock、统一工具栏窗口与 iOS 式手机主屏"
colors:
  accent: "#007aff"
  accent-hover: "#0068d9"
  label: "#1d1d1f"
  secondary: "#6e6e73"
  tertiary: "#8e8e93"
  separator: "#3c3c4324"
  window: "#f5f5f7"
  group: "#ffffff"
  sheet: "#fbfbfd"
  glass: "#fafafcb8"
  sidebar: "#ececf0c7"
  fill: "#7878801f"
  green: "#1f8a3c"
  orange: "#b25f00"
  red: "#d70015"
  dark-accent: "#0a84ff"
  dark-label: "#f5f5f7"
  dark-secondary: "#a1a1a6"
  dark-window: "#1e1e20"
  dark-group: "#2c2c2e"
  dark-glass: "#28282cb8"
typography:
  page-title:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Text\", \"PingFang SC\", \"Segoe UI\", \"Microsoft YaHei\", sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.3
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Text\", \"PingFang SC\", \"Segoe UI\", \"Microsoft YaHei\", sans-serif"
    fontSize: "13px"
    lineHeight: 1.45
  caption:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Text\", \"PingFang SC\", \"Segoe UI\", \"Microsoft YaHei\", sans-serif"
    fontSize: "11.5px"
  mono:
    fontFamily: "ui-monospace, \"SF Mono\", Menlo, Consolas, monospace"
    fontSize: "12.5px"
rounded:
  control: "8px"
  button: "999px"
  group: "12px"
  menu: "12px"
  window: "16px"
  sheet: "20px"
spacing:
  menubar: "30px"
  toolbar: "52px"
  sidebar: "210-220px"
  content: "22px 28px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "#ffffff"
    rounded: "{rounded.button}"
    height: "28px"
  button-secondary:
    backgroundColor: "{colors.group}"
    textColor: "{colors.label}"
    rounded: "{rounded.button}"
    height: "28px"
  toolbar-button:
    backgroundColor: "{colors.glass}"
    rounded: "{rounded.button}"
    height: "30px"
  input:
    backgroundColor: "{colors.group}"
    rounded: "{rounded.control}"
    height: "30px"
  dock-icon:
    width: "50px"
    height: "50px"
  desktop-icon:
    width: "58px"
    height: "58px"
---

# Design System: Gateway Desktop

## Overview

**North Star: "macOS 27 的桌面秩序，iOS 的手机主屏"**

网关的 80 端口页面是一张桌面：顶部是半透明菜单栏，底部是玻璃 Dock，壁纸上是用户添加的链接。控制面板、代理配置、局域网互传、Clash 面板和 AdGuard Home 都在同一页面的窗口里打开；只有工作站桌面（外部 HTTPS）在新标签页打开。

视觉参照 macOS 27：窗口使用统一圆角，标题与工具栏合并为一条玻璃工具栏，侧栏贴边并配彩色符号，设置内容使用内嵌分组列表。参考资料：
[9to5Mac](https://9to5mac.com/2026/06/09/macos-27-golden-gate-includes-these-changes-that-tahoe-critics-will-appreciate/)、
[MacRumors](https://macrumors.com/2026/06/09/macos-golden-gate-liquid-glass/)、
[Cult of Mac](https://www.cultofmac.com/news/liquid-glass-changes-ios-27-macos-27)、
[Michael Tsai](https://mjtsai.com/blog/2026/06/09/golden-gate-sidebars-and-toolbars/)。

**Key Characteristics:**
- 菜单栏：左侧是系统菜单和当前应用名，右侧是更新数、Tailscale 状态和时钟。
- Dock：系统应用固定在 Dock，运行中的应用显示圆点；最小化的窗口收进 Dock。
- 窗口：16px 圆角，52px 玻璃工具栏，红黄绿控制点在左，标题左对齐，操作按钮在右。
- 内容：浅灰窗口底上的白色分组列表；行左侧为彩色符号，右侧为路线标签、开关或操作。
- 亮色、暗色和跟随系统三种外观，同一套语义变量驱动。

## Colors

颜色以系统蓝为唯一操作强调色。标签文字分三级（主、次、三级），分隔线和填充色使用带透明度的灰。实际值以 `web/style.css` 开头的变量为准；`--blue`、`--text`、`--muted`、`--surface`、`--chrome`、`--line`、`--border`、`--selected`、`--danger` 是给登录页、图标和局域网互传样式保留的别名。

- **系统蓝**：主要按钮、选中的侧栏项、链接和焦点光圈。
- **绿 / 橙 / 红**：只用于状态胶囊、路线标签和破坏性操作，各自配浅色底。
- **玻璃**：菜单栏、Dock、菜单、工具栏和通知使用半透明底加背景模糊；`prefers-reduced-transparency` 下改为不透明。
- **彩色符号**：侧栏和列表行的 28px 符号底板使用蓝、紫、绿、橙等系统色，区分对象类型（设备、分组、出口、中转）。

## Typography

系统字体栈覆盖 macOS、Windows 与中文，不下载外部字体。正文 13px，页面标题 20px/700，分组标题 12px/600 次级色，说明文字 11.5–12.5px。IP、域名和 YAML 使用等宽字体。手机输入框使用 16px，避免 iOS 自动放大。

## Layout

### 桌面

- 菜单栏 30px，固定在顶部。
- 桌面链接从右上角起按列排列，网格 96 × 112px，图标 58px，名称最多两行。
- Dock 居中贴底，图标 50px，悬停时放大并显示名称。
- 窗口默认居中，可移动、缩放、最小化和最大化，不会盖住菜单栏和 Dock。

### 窗口内部

控制面板和代理配置都是“贴边侧栏 + 内容区”。侧栏 210–220px，内容最大宽度 780–860px 并居中。窗口宽度不足 720px 时隐藏侧栏，工具栏出现返回按钮，侧栏变成内容区里的分组列表。

### 手机（700px 以下）

- 主屏：顶部状态栏（时间在左），四列图标网格，底部 4 个应用的 Dock；其余系统应用以图标形式出现在主屏。
- 应用全屏打开，此时隐藏状态栏和 Dock；左上角 36px 关闭按钮返回主屏。
- 列表行改为两行：第一行是标题和开关或操作，第二行是路线标签、状态或下拉框。
- 常用控件至少 36–44px 高。

## Elevation & Depth

层级依次为：壁纸、桌面链接、窗口、Dock / 菜单栏、菜单和通知、模态对话框。窗口用两层阴影加 0.5px 描边，分组列表只用极浅描边，不用投影。

## Shapes

窗口 16px，对话框 20px，菜单 12px，分组列表 12px，输入框 8px，按钮为胶囊形。应用 SVG 使用 96 × 96 viewBox 和统一的圆角底板，`object-fit: contain` 保持比例。

## Components

### Toolbar

工具栏位于窗口标题栏内，空白处仍可拖动窗口。代理配置的工具栏显示“有未应用的更改”状态、放弃更改和应用；内嵌网页窗口的工具栏提供重新载入和在新标签页打开。

### Lists and rows

`list-row` 由符号、标题与副标题、尾部内容和行操作组成。可进入的行在末尾显示箭头，整行可点击。路线标签（`route-chip`）用颜色区分：出口为绿色，分组或中转为蓝色，直连为灰色，拦截为红色。

### Clash editor

代理配置分为三组页面：

- **分流**
  - 设备出口：IP、IP 段或网段 → 出口。设备的全部外网流量从所选出口发出。
  - 分组：名称 + 域名 + 出口。可以新建（例如 Google、YouTube）、改名、停用和删除，未匹配任何分组的流量由“其他网站”决定。
- **线路**
  - 出口：HTTP / SOCKS5 固定 IP 代理。“前置代理”默认选中转节点（设备 → 中转 → 出口），也可以设为“无”。
  - 中转订阅：机场订阅地址，从这里打开 Clash 面板。
- **高级**：全部规则（排序、搜索、筛选）和 YAML 编辑器。

所有修改先写入草稿，工具栏统一应用或放弃。编辑器发送与之前相同的草稿请求，应用流程不变；新增的只有删除出口、删除分组和批量添加域名。分组的出口是默认出口，在 Clash 面板中手动选过的节点优先。删除仍被设备、规则或其他分组使用的出口或分组时会说明原因并拒绝。

### Menus, alerts and notifications

- 菜单使用玻璃底，悬停项为蓝底白字。
- 确认框居中显示；破坏性操作使用红色图标和红色“删除 / 放弃”按钮。
- 通知在桌面右下角、Dock 上方，在手机上放在顶部安全区。成功提示会自动收起，错误提示会停留。

### Embedded apps

局域网互传、Clash 面板和 AdGuard Home 在窗口内通过 iframe 打开。局域网互传使用 `?embed=1` 隐藏自身标题，文件夹链接保持该参数，并跟随桌面的外观设置。nginx 为面板和 AdGuard 去掉上游的 `X-Frame-Options`，统一使用同源策略。

### Personalization

四张本地壁纸：晴日海岸（默认）、山湖晨光、海岸暮色、林间薄雾。用户可上传图片，并选择填充、适应、拉伸、居中或平铺。外观可选亮色、暗色或跟随系统，设置保存在网关上。

## Motion and accessibility

- 动效：过渡为 120–220ms；Dock 图标悬停时放大；对话框以轻微缩放出现。`prefers-reduced-motion` 会停用全部过渡和动画。
- 键盘：可聚焦元素显示 3px 蓝色焦点环；窗口控制点也支持键盘操作。
- 屏幕阅读器：纯图标按钮都有 `aria-label`。

## Do's and Don'ts

### Do

- 把新功能放进窗口里的设置页，或 Dock 里的应用，不放到桌面上。
- 列表优先用分组行；对象类型用彩色符号区分，操作强调色只用蓝色。
- 修改代理配置一律先进草稿，在工具栏统一应用。
- 在真实手机和 Safari / Firefox 上验收；浏览器响应式截图不能代替真机测试。

### Don't

- 不要在窗口内再画一条标题栏或独立的保存栏。
- 不要为功能模块另造主题色，也不要拉伸应用图标。
- 不要让通知或浮层盖住窗口工具栏的操作按钮。
