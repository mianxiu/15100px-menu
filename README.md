# Photoshop Menu

GitHub UI contract已在提交e5a07cc通过：[远端检查](https://github.com/mianxiu/15100px-menu/actions/runs/39902662542)。后续push／PR自动运行；未更改分支保护设置。

255／UXP0.3.65已更新本机：统一Caps、查找／拆分、颜色数值、tip及状态文字角色，全部原生操作跟随PS字号的95%，正文跟随PS字号，辅助信息小一级；保留预设尺寸／标签专用层级。后台使用统一字号／行高／字重变量，窄窗口只调整布局。新增原生／前端／冻结打包门禁及GitHub UI contract，违规直接失败；AGENTS.md强制后续沿用。完整[文字审计与规范](https://github.com/mianxiu/15100px-menu/wiki/UI-Typography)。

572项Python回归、45项前端测试、低CPU原生完整矩阵、三档字号当前主题预览及冻结启动／重启通过；实际255、dist与嵌入菜单／热键／网页资源一致，配置／PS会话／历史未知保持。故意注入未来视图的固定字体与内联字号，两类契约均确实拒绝。未宣称性能提升。

实屏检查开始前检测到QQ前台而安全暂停，未创建临时文档或提交PS命令，等待回到PS／Codex／Chrome后继续。后台浏览器自动化内核退出；浏览器桌面／窄屏视觉、实体拼音／键鼠、其他DPI／硬件／PS版本待验。公开下载仍254；255发布待本轮PS实屏核验。

[254已发布并更新本机](https://github.com/mianxiu/15100px-menu/releases/tag/v0.4.254)，内置UXP0.3.65：主ZIP／SHA256和Latest更新清单已匿名下载核验，ZIP内EXE与实际254一致；核验后删除230 Release及附件，发行页仅保留254，旧标签及源码历史保留。升级需正常重启PS加载UXP65，已加载65且文件一致时只更新主程序。

254／UXP0.3.65：在“逐层智能对象”右侧增加“单层智能对象”，共用分段外框、主题、留白和投影。单选转换当前层，多选同父组图层合成一个智能对象；沿用现有转换命令，默认F5行为不变。逐层转换仍各自生成独立智能对象，跨组选择只允许逐层转换。已发布254并核验公开下载。 [操作与验证范围](https://github.com/mianxiu/15100px-menu/wiki/Individual-smart-objects)。

253／UXP0.3.65已切换本机：查找／拆分复用Caps共享控件与主题；修正上移／下移底部多出的6单位边距，移除画布菜单遗留排序文字项及隐藏命中，启用Windows输入法定位、新汉字补字，并修复重开查找带回旧文字。后台图层搜索／文本工具页面已移除，PS内单独F查找和Caps拆分保留。投影沿用250的平滑缓存纹理，替代分层描边。570回归、43项前端测试、低CPU原生矩阵、冻结启动重启及实际入口／dist／组件核验通过；PS未重启，原稿／配置／历史未知保持。公开Release仍230。 [用法与验收限制](https://github.com/mianxiu/15100px-menu/wiki/Layer-search)／[共享UI规则](https://github.com/mianxiu/15100px-menu/wiki/Development)／[完整投影对照](https://github.com/mianxiu/15100px-menu/wiki/Menu-shadow)。

249／UXP0.3.65已切换本机：Caps 新增“逐层智能对象”，每个选中层各转一个，跨组保留父组与层序、整批一次撤销；已有智能对象跳过，F5 合并行为不变。568回归、35组Node、低CPU原生矩阵、8项后台真实PS及实际服务低CPU／正常各1项通过，零像素差与精确撤销，原稿／配置／历史未知保持。投影沿用248的Win11风格近似与诊断未响应修复；实体输入／GPU实屏／原低配待验，公开Release仍230。[逐层转换用法与限制](https://github.com/mianxiu/15100px-menu/wiki/Individual-smart-objects)。

248本机：修复原生长批次诊断渲染不处理窗口消息造成的可复现未响应；低CPU／正常WARP各8秒持续响应并正常关闭，566回归及冻结启动重启通过，实际入口／dist／原生组件一致。Caps改为Win11风格宽柔影＋接触影，保留布局和命中；它是透明控件组的外观近似。PS／UXP会话、配置及历史保护保持。截图进程身份未证实；正常WARP投影对照缺测、GPU实屏／实体输入及原低配待验。公开Release仍230。[原因与证据](https://github.com/mianxiu/15100px-menu/wiki/Menu-responsiveness)／[全部开销与限制](https://github.com/mianxiu/15100px-menu/wiki/Menu-shadow)。

247本机：普通Caps按钮组／色板／预设／中心环及底部信息加浅柔和投影，不改变命中、位置或PS执行；565回归、冻结构建和实际入口匹配通过。GPU帧提交中位增加约0.029～0.034ms（每侧200样本），CPU回退保留49.0815ms长帧；完整中位／P95／最大、绝对／百分比及未验范围见[投影测量](https://github.com/mianxiu/15100px-menu/wiki/Menu-shadow)。PS未重启，公开Release仍230。


246／UXP0.3.64本机：新建／调整图层图标下移到颜色标签右边；上移／下移及拆分文字移到原右侧位置，绘制与命中同步。565回归、低CPU原生矩阵、当前主题CPU布局及实际入口匹配通过，PS无需重启；实体手感／GPU实屏仍待验。[菜单布局](https://github.com/mianxiu/15100px-menu/wiki/Menu-guide)。公开Release仍230。


245／UXP0.3.64本机：图层菜单新增“文档顶／文档底”，可将单层、整组或同组多选移到文档根层级；原置顶／置底仍在组内排序。565回归、34组Node、真实PS低CPU／正常六组排序和一次撤销通过，已切换实际入口。[用法与限制](https://github.com/mianxiu/15100px-menu/wiki/Layer-sorting)。公开下载仍230。


244／UXP0.3.63本机：F打开鼠标附近单框自动搜索，类型直接点标签；文件名／图层名双字段和类型下拉已移除。空白处拖动，PS窗口内避让；Caps文字拆分保留。有限范围画布自动ENG已实现，输入恢复与未知保护保留，完整中文实体输入矩阵待验。公开下载仍230。[搜索用法](https://github.com/mianxiu/15100px-menu/wiki/Layer-search)／[ENG范围](https://github.com/mianxiu/15100px-menu/wiki/Input-language)。

233托盘恢复注册＋234更新完成前核对菜单／热键／托盘就绪已保留；另一台图标问题经用户重新启动已恢复，根因待复现，见[说明](docs/TRAY.md)。232／231读取优化的[速度与范围](https://github.com/mianxiu/15100px-menu/wiki/Layer-performance)。

227／UXP0.3.57起：后台新增图层搜索，按打开文档文件名、图层名与类型筛选，明确点击后按ID跨文档定位并保留隐藏状态。[操作和验证范围](https://github.com/mianxiu/15100px-menu/wiki/Layer-search)。

226／UXP0.3.56起：原生选层策略省去无效DOM反馈，保留写前与终态新鲜核验。513后端／28组Node和低CPU／正常22项真实PS接口检查通过；[速度与未验范围](https://github.com/mianxiu/15100px-menu/wiki/Layer-performance)。

[公开下载230](https://github.com/mianxiu/15100px-menu/releases/latest)／UXP0.3.59：图层搜索、文本拆分／替换与正常长任务自检修复。公开ZIP／SHA／Latest清单已匿名下载核验，仅保留230 Release，旧标签和源码历史保留。[用法与限制](https://github.com/mianxiu/15100px-menu/wiki/Caps-execution)。

以下为历史交付记录，反映当时状态；旧版链接指向保留的源码标签，发行页只保留最新版。

[218已发布并更新本机](https://github.com/mianxiu/15100px-menu/tree/v0.4.218)，UXP仍0.3.51：任务运行中按Caps打开的图层运行菜单，成功后经新鲜目标核验自动恢复固定普通菜单；公开ZIP／SHA／Latest清单及Wiki已核验。[操作与验证范围](https://github.com/mianxiu/15100px-menu/wiki/Menu-guide)。

[217已发布并更新本机](https://github.com/mianxiu/15100px-menu/tree/v0.4.217)，UXP仍0.3.51：自动测试保留原报告，增加核验后的原测试文档收尾，中文显示失败阶段及原始错误详情；ZIP／SHA／Latest清单公开核验通过。[使用和验证范围](https://github.com/mianxiu/15100px-menu/wiki/Stability-test)。

[216／UXP0.3.51已发布并更新本机](https://github.com/mianxiu/15100px-menu/tree/v0.4.216)：24.2.x常见根级单选按需读取邻层，组／多选保留有界全树；ZIP、SHA和更新清单公开下载通过。[读取策略和验证范围](https://github.com/mianxiu/15100px-menu/wiki/Layer-performance)。

[0.4.215已发布并更新本机](https://github.com/mianxiu/15100px-menu/tree/v0.4.215)：主题和字号每次PS启动只读取一次成功值，运行期间不轮询；实际需要UXP0.3.50。[操作与验证范围](https://github.com/mianxiu/15100px-menu/wiki/Layer-performance)。

[0.4.214已发布并更新本机](https://github.com/mianxiu/15100px-menu/tree/v0.4.214)：UXP0.3.49将后台主题／文档元数据读取放到菜单和命令之后，存活心跳保留独立元数据时间。实际48需正常关闭PS后更新内置49再手动启动；[性能与验证范围](https://github.com/mianxiu/15100px-menu/wiki/Layer-performance)。

[0.4.213已发布并更新本机](https://github.com/mianxiu/15100px-menu/tree/v0.4.213)：菜单空白处右键关闭，屏幕取色时右键先取消取色。UXP仍0.3.48，不需重启PS；[操作与验证范围](https://github.com/mianxiu/15100px-menu/wiki/Mask-preview)。

210本机修正24.2首页“当前文档不可用”弹窗；故障机需实际加载UXP0.3.48。[安装说明](https://github.com/mianxiu/15100px-menu/wiki/Stability-test)。[最新版本已发布](https://github.com/mianxiu/15100px-menu/releases/latest)。

本机209修正取色后重新hover收起：确认调整后返回普通菜单继续操作。UXP仍为0.3.47，未新增Release；实体鼠标和其他宿主待验。[说明](https://github.com/mianxiu/15100px-menu/wiki/Mask-preview)。

[208已发布](https://github.com/mianxiu/15100px-menu/tree/v0.4.208)／UXP0.3.47：针对PS24.2.x逐属性DOM读取延迟，改用有界批量标量读取与新鲜身份核对，沿用原能力算法和写前校验；仅显式颜色元数据采用短时只读模态。自动测试补齐标准54次／持续180次原生菜单显示、请求／接收、按钮能力、内容帧和收起，记录心跳失鲜及最后菜单观测。需保存文档、正常关闭PS后更新内置UXP，再手动启动并确认实际0.3.47。

[使用说明和验证边界](https://github.com/mianxiu/15100px-menu/wiki/Stability-test)。PS24.2.0故障机仍待复测；实体Caps、UU远程及调色面板提前关闭未计为已修复。以下为此前版本记录。

[v0.4.207已发布](https://github.com/mianxiu/15100px-menu/tree/v0.4.207)／UXP0.3.46新增后台一键自动稳定性测试，自动生成图层读取、持续操作及系统负载报告。[使用方法与验证限制](https://github.com/mianxiu/15100px-menu/wiki/Stability-test)；故障机持续卡顿和UU远程Caps双按仍待定位。

以下为历史版本变更。

v0.4.206／UXP45已完成本机更新：修正慢图层读取让行、首份快照等待及预览遗留文件清理。两台Win11故障机待验收，公开Release仍205；操作与限制见[Wiki](https://github.com/mianxiu/15100px-menu/wiki/Layer-performance)。

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
