---
name: "251 Gateway Desktop"
description: "蓝色海岸主题的轻量网关桌面与二级设置后台"
colors:
  primary: "#075cff"
  primary-hover: "#004cdd"
  surface: "#ffffff"
  chrome: "#f2f4f7"
  sidebar: "#e9edf1"
  field: "#f3f5f7"
  text: "#30343b"
  muted: "#5a6470"
  border: "#d9dee5"
  selected: "#edf4ff"
  danger: "#c9343f"
  success: "#18724a"
  dark-surface: "#222932"
  dark-chrome: "#2b333e"
  dark-text: "#e9eef6"
  dark-muted: "#b1bdcc"
  dark-accent: "#8ab7ff"
  dark-success: "#8bdbb0"
typography:
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif"
    fontSize: "19px"
    fontWeight: 600
    lineHeight: 1.4
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
    padding: "8px 18px"
    height: "38px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "8px 18px"
  input:
    backgroundColor: "{colors.field}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "10px 13px"
    height: "40px"
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
- 设置分层、文件上传优先、手机端完整设置页面。
- 亮色、暗色和跟随系统的自动模式。

## Colors

主色是明亮的操作蓝；浅冷灰区分窗口外壳、侧栏、输入区与分隔线。实际值以前面的令牌和 `web/style.css` 为准。

### Primary
- **操作蓝**：主要按钮、链接、选中边框与焦点。
- **悬停深蓝**：亮色主要按钮的悬停反馈。

### Neutral
- **白色内容面**和**冷灰窗口壳**：设置内容与标题栏。
- **浅灰侧栏**与**浅灰输入区**：导航和可编辑区域。
- **深灰正文**与**辅助灰文字**：正文、说明及占位文字。
- **深色窗口面**、**浅色正文**和**浅蓝强调**：暗色主题的对应角色；实心主按钮仍保持操作蓝。

**The Single Accent Rule.** 操作强调使用蓝色；彩色应用图标和壁纸承担其余颜色，避免为设置模块各造一套颜色。

## Typography

系统字体栈同时覆盖 macOS、Windows 与中文，无外部字体下载。内容标题为 19px、600、1.4 行高，正文为 14px，说明与菜单主要使用 12px；手机标题降为 18px，输入文字使用 16px。正文段落最大宽度为 72ch。桌面图标名称为 14px，手机为 13px；窗口标题为 14px、600。

## Layout

桌面图标从左侧按列排列，112px 网格配合 18px × 30px 间距，图标实际为 64px。700px 以下改为三列行式网格、62px 图标与 18px × 6px 间距。顶部保留工具栏，主页保持图标入口。

桌面设置由 WinBox 承载，可移动、缩放、最小化与最大化；48px 标题栏下方排列 202px 侧栏和可滚动内容面。900px 以下侧栏缩至 176px；700px 以下窗口铺满可用页面，导航横向滚动，隐藏桌面缩放与最小化控件。

图标选择器使用六列纯图标网格，手机四列；每个选择按钮至少 60px 高，内部图标 40px。桌面和手机均使用同一 52 项本地图标目录，其中包括 Hermes 与 WorkBuddy。

## Elevation & Depth

窗口阴影表达桌面层级，浅灰侧栏与白色内容面表达窗口内部结构。右键菜单、确认框和个性化设置叠在桌面之上，背景遮罩使用轻微模糊。

- 窗口：`0 20px 64px #14314240, 0 4px 16px #14314214`。
- 深色窗口：`0 20px 64px #08101970, 0 4px 16px #08101933`。
- 右键菜单：`0 10px 32px #14364240, 0 2px 8px #1436421a`。

## Shapes

应用 SVG 使用 96 × 96 viewBox，76 × 76 底板位于 (10, 8)，圆角 21。图像用 `object-fit: contain` 保持比例。表单与按钮圆角 7px，菜单 9px，窗口 12px，普通对话框 13px。窗口左上方采用红黄绿控制点，手机将关闭操作扩大为 44px 命中区域并保留红色圆点。

## Components

### Desktop shortcuts and icon picker

桌面快捷方式是图标加名称；选择器是纯图标。选中项使用浅蓝底与蓝色边框，名称仅由悬停 `title` 与 `aria-label` 提供；方向键、Home、End 可移动焦点。搜索按名称、ID 和分类筛选。图标均由本地 SVG 提供，不加载远程图标或字体。

### Buttons and forms

主要按钮蓝底白字，次要按钮使用内容面、细边框与正文色。悬停改变底色和边框；键盘焦点为 2px 蓝色描边，偏移 3px。输入区使用浅灰底，聚焦后转为内容面并显示蓝色边框。常规按钮 38px，手机常用按钮至少 44px。原生表单语义保留，视觉样式由页面定义。

### Settings and proxy configuration

设置汇总使用分组图标入口；具体设置提供侧栏导航。Clash/Mihomo 主流程是上传 YAML 文件、查看或编辑、保存并应用；订阅链接留在高级设置。账户页面提供登录后修改密码和退出。广告过滤、Tailscale、DNS、升级、桌面管理与备份保持独立设置入口。

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
- 不要恢复系统默认下拉框或混用不同风格的应用图标。
- 不要在纯图标选择区增加逐项文字、文件路径或卡片说明。
- 不要拉伸图标或用大号线条菜单图形替代彩色应用底板。
- 不要把管理表单、长说明和全部服务状态堆到桌面首页。
- 不要把截图或浏览器检查当作真实手机硬件验收。
