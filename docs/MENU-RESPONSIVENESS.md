# MenuHost 诊断渲染未响应修复（248）

247的长批次原生渲染测速在UI线程连续绘制、轮询DX11完成，未处理消息队列。独立自建WARP测试进程已复现Windows IsHungAppWindow=true、29次WM_NULL探针超时和关闭消息500ms未处理；只结束了该自建只读测试进程，没有结束PS或实际服务。Windows会在顶层窗口数秒不响应时创建幽灵窗口：[Microsoft消息队列说明](https://learn.microsoft.com/en-us/windows/win32/winmsg/about-messages-and-message-queues)。

248在每帧、DX11等待和250ms闲置等待中共用正常渲染消息泵，处理关闭后退出并释放查询资源；取消不输出完整测速文件。未禁用Windows挂起检测，未增加产品输入等待或PS读取。正常生产循环保持原消息处理语义。

## 证据及边界

截图没有PID，当前247实际菜单探针曾正常响应，未找到对应Application Hang1002记录；旧WER是10月10–18日旧路径AppCrash/BEX64。因此已修复可重复证明的同类诊断挂起，不能断言截图一定来自该进程，亦不能宣布所有生产挂起根因已排除。

最终248 WARP低CPU（双逻辑处理器Below Normal）／正常各8秒，先等待benchmark.started再探测真实窗口，Windows无挂起、所有探针响应，WM_CLOSE正常退出0且未写完成数据。247基线80ms探针和248 300ms上限不同，247大量超时是下界，不能算响应提速百分比。完整原始样本.runtime/hang248-baseline/report.json、.runtime/hang248-verified/report.json；并列统计只说明响应与取消恢复，不冒充物理按键到屏幕延迟。

|版本／配置|n|WM_NULL 中位/P95/最大 ms|超时／Windows挂起|正常关闭 ms|
|---|---:|---|---|---|
|247 WARP原诊断|原始样本见报告|29次80ms探针超时，无可比完成时间|29／已出现|500ms未处理关闭|
|248 WARP/low|143|5.1010 / 12.6665 / 14.9090|0／无|28.407|
|248 WARP/normal|141|5.4172 / 13.6115 / 15.1083|0／无|141.120|

566项回归（含WARP持续响应与正常关闭）、最终冻结EXE启动／重启、实际248／UXP64、dist及菜单／热键资源核验通过。PS未重启，同会话、用户配置、195历史未知与无当前pending均保持；低CPU／正常各2次自身托盘恢复注册通过。公开Release仍230。

Win11风格投影与完整开销见[投影测量](https://github.com/mianxiu/15100px-menu/wiki/Menu-shadow)。正常WARP投影测速前自测断言失败独立保留；GPU离屏缺失、真实PS实屏／实体键鼠、原故障低配设备未验。若实际服务再次未响应，需要记录对应PID与日志，不能用本次诊断修复替代现场归因。
