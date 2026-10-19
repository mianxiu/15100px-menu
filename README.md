# Photoshop Menu

v0.4.202：修复色相／邻近色提示跳位和空白误报色相。详情见[Wiki](https://github.com/mianxiu/15100px-menu/wiki/Perceptual-color)。

v0.4.201：展开／收起统一悬停原按钮，说明文字保留，外框恢复实线。用法与验证范围见[Wiki](https://github.com/mianxiu/15100px-menu/wiki/Perceptual-color)。

v0.4.200：展开／收起按钮增加状态说明文字及圆角虚线描边，沿用点击收起与屏幕取色保护。用法和验证范围见[Wiki](https://github.com/mianxiu/15100px-menu/wiki/Perceptual-color)。

v0.4.199：颜色／羽化面板仅点击原图标收起，屏幕取色后往返保持展开。用法与验证限制见[Wiki](https://github.com/mianxiu/15100px-menu/wiki/Perceptual-color)。

本机v0.4.197将所有成功反馈统一为勾号短暂停留后自动收起菜单，使用说明见[Wiki菜单指南](https://github.com/mianxiu/15100px-menu/wiki/Menu-guide)。

本机v0.4.196已增加屏幕吸管、完整面板连接通道及拖动后保持展开；操作与验证范围见[Wiki取色说明](https://github.com/mianxiu/15100px-menu/wiki/Perceptual-color)。

为 Windows Photoshop 提供随鼠标唤出的快捷菜单，让选层、排序、创建图层与调色更顺手。

[下载最新版](https://github.com/mianxiu/15100px-menu/releases/latest) · [使用文档](https://github.com/mianxiu/15100px-menu/wiki) · [安装指南](https://github.com/mianxiu/15100px-menu/wiki/Installation) · [反馈问题](https://github.com/mianxiu/15100px-menu/issues)

## 主要功能

- **随处唤出**：按 CapsLock 打开环绕菜单，根据画布、图层面板或首页显示对应操作。
- **快速处理图层**：选择相邻／组内图层、置顶置底、上下移动、颜色标签、复制粘贴样式及转换智能对象。
- **创建与调色**：新建空白、填充与调整图层；方块取色、按形状区分的联动感知配色与渐变、形状填充／描边复制并批量粘贴，羽化／密度支持拖动和数值输入；悬停展开调色面板，实时预览、取消恢复及范围见 [Wiki](https://github.com/mianxiu/15100px-menu/wiki/Shape-paint-clipboard)。
- **版本自动自检**：版本或能力变化后自动检查、异常留证，在后台查看与导出；[范围与限制](https://github.com/mianxiu/15100px-menu/wiki/Version-health)。
- **独立后台管理**：下拉配置快捷键，管理本地插件、检查更新、查看任务和导出诊断；菜单与后台跟随 PS 明暗主题。

## 界面预览

**图层快捷菜单**

![图层菜单：排序、创建、颜色标签和调色展开图标](docs/images/layer-menu.png)

**悬停展开调色面板**

![颜色与羽化面板：普通色相条、感知配色及数值滑条](docs/images/color-editor.png)

**后台快捷键设置**

![后台管理：使用下拉框配置菜单与图层快捷键](docs/images/shortcut-settings.png)

菜单图为v0.4.194原生渲染器的示例导出；后台图来自 v0.4.155 实际运行页面。

## 开始使用

需要 **Windows 10／11 x64**；v0.4.198起声明最低 **Photoshop 23.3.0／UXP6.0**（23.x实机待验，当前已验PS24.0.1）。版本兼容与已知限制见 [Wiki](https://github.com/mianxiu/15100px-menu/wiki/Installation)。

1. 从 [Release](https://github.com/mianxiu/15100px-menu/releases/latest) 下载 `PhotoshopMenu-Backend-<版本>.zip`，解压并运行 `PhotoshopMenu.exe`，无需安装 Python 或 Node.js。
2. 双击托盘图标打开后台，在「插件管理」按提示安装内置 UXP 插件，重新打开 PS，确认已连接。
3. 在 PS 画布或图层面板按 **CapsLock**：短按固定菜单，长按划向操作后松键执行；回中心或按 Esc 取消。

## 更多说明

[操作与默认快捷键](https://github.com/mianxiu/15100px-menu/wiki/Menu-guide) · [插件安装与更新](https://github.com/mianxiu/15100px-menu/wiki/Installation) · [故障排查](https://github.com/mianxiu/15100px-menu/wiki/Troubleshooting) · [开发与构建](https://github.com/mianxiu/15100px-menu/wiki/Development)

详细用法、性能测试、已知限制和[历史记录](https://github.com/mianxiu/15100px-menu/wiki/Readme-archive-2026-10-17)统一收录于 Wiki；开发待办见 [TODO](TODO.md)。

## 许可

[MIT](LICENSE)。第三方库与字体遵循各自许可，见[第三方许可说明](THIRD_PARTY_NOTICES.md)。
