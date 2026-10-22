# 托盘图标

后台运行时，主屏右下角通知区或“^”折叠区中有 Photoshop Menu 图标，悬停名称为“Photoshop Menu - Actions”。双击打开后台管理，右键可打开后台或正常退出服务。也可重新打开原启动快捷方式进入已有服务，无需结束进程或重启PS。

233起监听Windows的`TaskbarCreated`通知，在Explorer恢复后重新注册图标；通知重复时更新已有图标。启动或恢复注册失败时，每秒重试一次、最多5次，随后等待下一次恢复通知；失败保留在状态`tray_error`，恢复成功才清空。保留Windows的折叠／固定偏好，不强制修改任务栏设置。

本机实际234／UXP0.3.61已核验，PS保持原会话。541项后端测试、冻结EXE启动／重启及真实Shell恢复通过；实际服务低CPU／正常各2次恢复，重复通知通过，配置、旧未知记录与资源设置保持。测试仅删除本程序图标并向其窗口发送恢复通知，未重启Explorer。

234起更新助手会等待菜单窗口、菜单／热键进程及托盘线程正常、托盘注册无错误后，才报告更新完成；不再将HTTP开始响应当作启动完成。后台静默启动仍要求桌面组件就绪，明确的无桌面模式不要求托盘。健康检查只读取本地启动状态，不查询PS。原目标、空闲更新、正常退出及失败不强制结束保护保持。注册正常仍可能位于折叠区，这项判断不证明实体可见性。

隔离233→234真实EXE更新，低CPU／正常各一次：使用本地已校验候选暂存文件，经生产安装接口及独立新版助手替换／重启，确认就绪后才完成；配置和安装收据保持，正常退出。不是公开下载测试。首次冻结验证和实际入口核验都捕获到菜单创建早于整体就绪，测试等待已同步修正；原失败日志保留，未重发PS操作。不是速度优化，不宣称提速。

2026-10-22用户澄清故障发生在另一台电脑，可能在更新后；再次点击启动入口已恢复，发生时版本／日志未记录，根因仍未确认。本机原232图标有Shell注册且Explorer未重启，仅是本机检查，不能代表另一台。画面工具因`CreateProcessSecurityEnvironment`错误0x80070020无法启动，实体可见性、真实Explorer重启及原机器复现未验。公开下载仍为230。

证据：`.runtime/tray234/report.json`、`update234/*/report.json`、`tests234.log`、`smoke234-final.log`；原就绪时序记录`smoke234-before-ready-wait.log`及`tray234/early-readiness-observation.json`。系统行为参考[Microsoft任务栏文档](https://learn.microsoft.com/en-us/windows/win32/shell/taskbar)及[通知区文档](https://learn.microsoft.com/en-us/windows/win32/shell/notification-area)。
