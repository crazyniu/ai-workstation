---
name: "251 Gateway Desktop"
description: "蓝色海岸主题的轻量网关桌面与二级设置后台"
colors:
  primary: "#075cff"
  primary-hover: "#004cdd"
  surface: "#ffffff"
  canvas: "#f4f6f9"
  chrome: "#eef1f5"
  sidebar: "#e9edf2"
  field: "#f5f7f9"
  text: "#262b32"
  muted: "#5d6773"
  border: "#d4dae2"
  line: "#e4e8ed"
  selected: "#e6efff"
  danger: "#c42f3b"
  success: "#17704a"
  warning: "#8a5300"
  dark-surface: "#232a33"
  dark-canvas: "#1b2129"
  dark-chrome: "#2a323d"
  dark-text: "#e8edf5"
  dark-muted: "#a9b6c6"
  dark-accent: "#8ab7ff"
  dark-success: "#8bdbb0"
  dark-warning: "#f2c26f"
typography:
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif"
    fontSize: "22px"
    fontWeight: 650
    lineHeight: 1.3
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif"
    fontSize: "14px"
    lineHeight: 1.75
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif"
    fontSize: "12px"
  toast:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif"
    fontSize: "13px"
    lineHeight: 1.6
rounded:
  control: "7px"
  card: "10px"
  menu: "9px"
  window: "12px"
  dialog: "13px"
spacing:
  small: "6px"
  control-inline: "18px"
  content: "30px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#ffffff"
    rounded: "{rounded.control}"
    padding: "7px 14px"
    height: "36px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "7px 14px"
  input:
    backgroundColor: "{colors.field}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
    height: "38px"
  application-icon:
    width: "64px"
    height: "64px"
  picker-icon:
    width: "40px"
    height: "40px"
---

# Design System: Gateway Desktop

## Overview

**Creative North Star: "蓝色海岸上的轻量 NAS 桌面"**

蓝色海岸壁纸承托图标与名称，白色设置窗口保留熟悉的桌面秩序。彩色图标采用同一浅色圆角底板；主要操作使用清晰的蓝色按钮，内容与设置停留在二级界面。

桌面保持轻量、疏朗，管理表单采用紧凑而有留白的布局。深色模式通过同一组语义变量切换窗口、表单、编辑器与菜单的表面和文字；自动模式跟随系统偏好，保持同一布局与图标比例。

**Key Characteristics:**
- 蓝色自然摄影壁纸与白色浮动窗口。
- 统一彩色应用图标和纯图标选择网格。
- 控制面板以概览为首页：状态卡片汇总网关、Tailscale 与版本，全部设置按网络、桌面与账户、系统分组。
- 具体设置使用卡片与设置行：左侧标题与说明，右侧开关或操作；手机端通过“所有设置”返回概览。
- 亮色、暗色和跟随系统的自动模式。

## Colors

主色是明亮的操作蓝；浅冷灰区分窗口外壳、侧栏、内容底与分隔线，白色卡片承载设置。实际值以前面的令牌和 `web/style.css` 开头的变量为准。

### Primary
- **操作蓝**：主要按钮、链接、选中边框与焦点。
- **悬停深蓝**：亮色主要按钮的悬停反馈。

### Neutral
- **白色卡片**、**浅灰内容底**和**冷灰窗口壳**：设置卡片、内容区与标题栏。
- **状态色**：成功绿、提醒琥珀、危险红仅用于状态胶囊、提示条与破坏性操作，各自配浅色底。
- **浅灰侧栏**与**浅灰输入区**：导航和可编辑区域。
- **深灰正文**与**辅助灰文字**：正文、说明及占位文字。
- **深色窗口面**、**浅色正文**和**浅蓝强调**：暗色主题的对应角色；实心主按钮仍保持操作蓝。

**The Single Accent Rule.** 操作强调使用蓝色；彩色应用图标和壁纸承担其余颜色，避免为设置模块各造一套颜色。

## Typography

系统字体栈同时覆盖 macOS、Windows 与中文，无外部字体下载。页面标题为 22px、650，卡片标题 14.5px、600，正文与设置行标题 14px，说明文字 12.5px；手机页面标题降为 20px，输入文字使用 16px。地址等技术值使用等宽字体。正文段落最大宽度为 72ch。桌面图标名称为 14px，手机为 13px；窗口标题为 14px、600。

## Layout

桌面图标从左侧按列排列，112px 网格配合 8px × 20px 间距，图标实际为 64px。700px 以下改为三列行式网格、62px 图标与紧凑间距。顶部保留工具栏，主页保持图标入口。

桌面设置由 WinBox 承载，可移动、缩放、最小化和最大化。标题栏下方为 236px 侧栏（搜索框、概览与全部分组入口）和独立滚动的浅灰内容区，内容最大宽度 860px。窗口宽度低于 720px 时隐藏侧栏，概览的设置入口变为分组列表，子页面顶部固定“所有设置”返回按钮；手机全屏显示设置。

图标选择器使用六列纯图标网格，手机四列；每个选择按钮至少 60px 高，内部图标 40px。桌面和手机均使用同一 52 项本地图标目录，其中包括 Hermes 与 WorkBuddy。

## Elevation & Depth

窗口阴影表达桌面层级，浅灰侧栏、浅灰内容底与白色卡片表达窗口内部结构；卡片只用细边框和极浅阴影，可点击卡片悬停时加深阴影。右键菜单、确认框和个性化设置叠在桌面之上，背景遮罩使用轻微模糊。

- 窗口：`0 20px 64px #14314240, 0 4px 16px #14314214`。
- 深色窗口：`0 20px 64px #08101970, 0 4px 16px #08101933`。
- 右键菜单：`0 10px 32px #14364240, 0 2px 8px #1436421a`。

## Shapes

应用 SVG 使用 96 × 96 viewBox，76 × 76 底板位于 (10, 8)，圆角 21。图像用 `object-fit: contain` 保持比例。表单与按钮圆角 7px，卡片 10px，菜单 9px，窗口 12px，普通对话框 13px。窗口左上方采用红黄绿控制点，手机将关闭操作扩大为 44px 命中区域并保留红色圆点。

## Components

### Desktop shortcuts and icon picker

桌面快捷方式是图标加名称；选择器是纯图标。选中项使用浅蓝底与蓝色边框，名称仅由悬停 `title` 与 `aria-label` 提供；方向键、Home、End 可移动焦点。搜索按名称、ID 和分类筛选。图标均由本地 SVG 提供，不加载远程图标或字体。

### Buttons and forms

主要按钮蓝底白字，次要按钮使用内容面、细边框与正文色，危险操作使用红字或红底。行内图标按钮（编辑、移动、删除）无边框，悬停显示浅底。键盘焦点为 2px 蓝色描边；输入区使用浅灰底与细边框，聚焦后转为内容面并显示蓝色边框和浅蓝光圈。开关用于即时可见的布尔设置，需要密码确认的更改在开关变化后才显示确认区。常规按钮 36px、输入 38px，手机常用控件至少 44px。原生表单语义保留，视觉样式由页面定义。

### Settings and proxy configuration

概览页顶部三张状态卡片显示网关地址与服务状态、Tailscale 连接与地址、网关 Web 版本与可用更新数；下方是带说明的设置卡片入口。侧栏搜索按名称与关键词筛选，回车打开第一项；Tailscale 项显示连接状态圆点，服务升级项显示可用更新数。每个设置页由页标题、说明和若干卡片组成：状态用胶囊（绿色已连接、琥珀待处理、蓝色进行中、红色异常），说明用提示条，恢复备份等破坏性操作放在红色边框卡片中，并在选择文件且确认后才可执行。Clash/Mihomo 编辑器沿用同一侧栏与表格样式，表单和 YAML 代码编辑同一份草稿，YAML 编辑器填满窗口高度，可上传、下载或保存并应用。桌面 Clash 图标打开此页，节点面板从页首进入。出口与订阅、直连地址、分流规则和自定义配置项分别展示。规则列表显示来源与顺序，可搜索、筛选和分页。账户页面提供登录后修改密码和退出。广告过滤、Tailscale、DNS、升级、桌面管理与备份保持独立设置入口。

### Context menu

桌面与图标提供自定义右键菜单。菜单宽 206px，内边距 6px，条目为 12px；悬停或键盘焦点使用蓝底白字。手机以相同视觉语言提供可触摸操作。

### Personalization

四张本地默认壁纸为晴日海岸、山湖晨光、海岸暮色和林间薄雾，海岸为默认。用户可上传图片，选择填充、适应、拉伸、居中或平铺；亮色、暗色、自动主题使用分段选择。自动主题响应系统颜色偏好，设置保存后保持。

### Motion and accessibility

操作反馈统一使用桌面右上角的全局 Toast，手机放在顶部安全区。Toast 使用内容面、窗口阴影、状态图标和关闭按钮，不改变设置内容的布局；通过顶层 popover 覆盖窗口和原生对话框。成功提示自动收起，错误提示停留更久，鼠标悬停或键盘聚焦时暂停计时。

界面状态使用 120ms ease-out 的背景和边框过渡。`prefers-reduced-motion: reduce` 会停用过渡、动画及平滑滚动。反馈和错误信息保持文本形式；纯图标选择项保留可访问名称。

## Do's and Don'ts

### Do:
- 沿用已有的蓝色海岸桌面、统一图标底板和窗口层级。
- 所有应用图标保持正方形并使用 object-fit: contain。
- 图标选择区只显示图形，通过 title 和 aria-label 提供名称。
- 将配置、服务升级、备份和账户操作放在设置的二级页面。
- 手机端保留至少 44px 的常用操作触摸区域，并遵循减少动态效果偏好。

### Don't:
- 下拉框沿用主题颜色和原生选择行为，应用图标使用统一风格。
- 不要在纯图标选择区增加逐项文字、文件路径或卡片说明。
- 不要拉伸图标或用大号线条菜单图形替代彩色应用底板。
- 不要把管理表单、长说明和全部服务状态堆到桌面首页。
- 不要把截图或浏览器检查当作真实手机硬件验收。
