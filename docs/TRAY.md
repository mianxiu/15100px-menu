# 托盘图标

后台运行时，主屏右下角通知区或“^”折叠区中有 Photoshop Menu 图标，悬停名称为“Photoshop Menu - Actions”。双击打开后台管理，右键可打开后台或正常退出服务。也可重新打开原启动快捷方式进入已有服务，无需结束进程或重启PS。

233起监听Windows的`TaskbarCreated`通知，在Explorer恢复后重新注册图标；通知重复时更新已有图标。启动或恢复注册失败时，每秒重试一次、最多5次，随后等待下一次恢复通知；失败保留在状态`tray_error`，恢复成功才清空。保留Windows的折叠／固定偏好，不强制修改任务栏设置。

本机实际233／UXP0.3.61已核验，PS保持原会话。537项后端测试、冻结EXE启动／重启、真实Shell注册及删除本程序图标后恢复通过；实际服务低CPU／正常各2次恢复，重复通知通过，配置、旧未知记录与资源设置保持。测试仅删除本程序图标并向其窗口发送恢复通知，未重启Explorer。

2026-10-22用户报告进程存在但看不到图标：原232图标仍注册，Explorer自服务启动后未重启，故不能认定恢复缺口就是该次原因。不同临时图标与原服务返回相同通知区矩形，提示可能位于折叠区；注册及矩形均不能证明图标实际可见。画面工具因`CreateProcessSecurityEnvironment`错误0x80070020无法启动，实体可见性与真实Explorer重启仍未验。公开下载仍为230。

证据：`.runtime/tray233/report.json`、`tests233.log`、`smoke233.log`。系统行为参考[Microsoft任务栏文档](https://learn.microsoft.com/en-us/windows/win32/shell/taskbar)及[通知区文档](https://learn.microsoft.com/en-us/windows/win32/shell/notification-area)。
