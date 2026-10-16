# 非输入场景自动切换 ENG：可行性评估

2026-10-15；评估基于实际运行 v0.4.133／UXP 0.3.13。没有实现或启用自动切换，没有修改键盘布局、IME设置或PS文档。

2026-10-16同步：实际146／UXP18仍未启用自动ENG；只读观察作为后续评估，不因Caps意图或F5变更自动开启切换。本文133／UXP13测量为历史基线。

## 结论

切换英文布局的系统能力可用，现有识别不足以保证排除所有文字编辑／图层重命名。可继续做只读观察验证；暂不应默认开启“其余所有情况强制ENG”。

让快捷键不等待检测／切换在架构上可行，但这不等于保证切换后的第一枚按键已由ENG处理。外部异步事件、焦点识别、消息投递和PS处理之间存在时序窗口；不能用缓存或延时掩盖这一限制。若要求每个首键必定ENG且完全不增加等待，当前进程外方案尚无依据承诺两者同时成立。

## 当前项目的实际能力

| 信息 | 已有能力 | 对自动切换的限制 |
| --- | --- | --- |
| PS前台范围 | 已知工作区／进程识别，原生钩子读取本地配置 | 可复用；外部应用、切换空窗、未知窗口不能当作允许切换 |
| 标准输入框 | `backend/panel_context.py`识别Edit、RichEdit20W、RichEdit50W、ComboBox焦点 | 这些类名不能覆盖PS所有自绘输入框；现有单元测试不是所有重命名场景的实机验收 |
| 图层／画布／首页 | 鼠标位置、点击及控件链分类 | 鼠标在画布不代表正在编辑文字，也不代表键盘焦点已经退出重命名；禁止用hover作为切换依据 |
| 输入焦点刷新 | `backend/desktop.py`约100ms工作线程刷新，配置发给原生热键 | 留有陈旧窗口，不适合直接决定强制ENG；已有快捷键末端保护也不证明输入语言策略完整 |
| 文字工具与图层类型 | 有选择类型快照 | 选中文字图层不等于正在输入，选中像素层也可能重命名；需要独立编辑状态证据。首轮可保守保护整个文字工具状态，但仍需验证 |
| 系统插入光标 | 可读取GUI线程的caret／focus／menu信息 | 有插入光标可作为禁止切换信号，未暴露光标不证明没有输入；后台或焦点切换时句柄可能为空 |
| UXP事件 | 当前监听select、make、delete、set、undo、redo，更新选择缓存 | 不是完整文字编辑开始／结束协议，不可由“没有事件”推断安全；插件模态期间通知也可能静默 |

## Windows能力与边界

- 优先目标是已安装的英文键盘布局，不把“中文IME里的英文模式”当作同一状态。`GetKeyboardLayout(thread)`可读PS线程布局，不能单独判断IME组合输入或自绘编辑状态。[GetKeyboardLayout](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getkeyboardlayout)、[GetKeyboardLayoutList](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getkeyboardlayoutlist)。
- 直接在后台调用`ActivateKeyboardLayout`只作用于调用线程／当前进程，不能据此声称切换了PS。[ActivateKeyboardLayout](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-activatekeyboardlayout)。
- 可向目标焦点窗口投递`WM_INPUTLANGCHANGEREQUEST`，但接收程序可拒绝；投递成功不是已经生效。须异步读回目标线程布局。消息排队后仍可能遇到焦点状态变化；即使投递前再次检查也不能完全消除窗口。[WM_INPUTLANGCHANGEREQUEST](https://learn.microsoft.com/en-us/windows/win32/winmsg/wm-inputlangchangerequest)。
- 不采用模拟Shift／Win+Space循环切换：方向受当前状态和安装顺序影响，还会加入额外按键。也不修改系统全局默认输入法或Windows“每窗口输入法”偏好。
- UI Automation可以提供额外输入控件信息，但必须独立线程处理，不能进低级键盘钩子或菜单唤出等待路径；自绘控件仍需验证其实际暴露能力。[UI Automation线程要求](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-threading)。
- 可使用按PS进程过滤的焦点／caret／菜单WinEvent作为观察候选，进程外通知是异步送达，不能承诺没有检测延迟。[SetWinEventHook](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwineventhook)、[GetGUIThreadInfo](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getguithreadinfo)。
- UXP通知可作补充，不作为唯一输入锁。Adobe明确非交互executeAsModal期间事件通知可静默，模态脚本范围事件也不等于所有原生文本编辑事件。[Adobe模态与事件通知](https://developer.adobe.com/photoshop/uxp/2022/ps-reference/media/executeasmodal)。

## 本机只读探测

已枚举到`0x04090409`（英文）与`0x08040804`（中文）。PS GUI线程当时为中文布局，PS不在前台，focus／caret为空；这是未知状态，不是允许切换的证据。

预热50次后，2000次`GetGUIThreadInfo + GetKeyboardLayout`配对读取中位4.5µs、P95 8.4µs、最大130.4µs。该数字包含Python ctypes调用，只反映本机空闲／后台状态的读取成本；没有测量UIA、切换生效时间、热键新增成本或按键到首帧延迟，不能外推为自动切换功能已无性能影响。证据`.runtime/eng-assessment133-readonly.json`。

## 后续应先验证的方案

1. 单独的只读观察模式：记录焦点／控件类、caret、菜单／模态和可获得的编辑状态及事件到达时间；不记录文字内容、不切换输入法。实际覆盖文字输入／修改、图层及组重命名、Tab连续重命名、属性／变换／图层样式数值、搜索、弹窗和候选／组合输入。
2. 三态判定：明确输入、明确非输入、未知。只有明确非输入才允许尝试；未知、失效、菜单／弹窗、组合输入或退出PS一律不发切换请求。不能将“没检测到标准Edit”当作非输入。
3. 仅在已验证的焦点转换后尝试切换，携带PS进程／线程／窗口及状态代次；发送前重新核验，异步读回，不排队等待多个旧切换、不在键盘回调里查询UIA／COM／UXP或等待PS。恢复输入时，仅考虑恢复本功能实际改变的布局；不擅自强制开启中文，不覆盖用户手动选择。此恢复行为尚待实测。
4. 验收必须同时检查误切换与漏切换：中文首字、候选选词、快速进入／退出重命名和跨应用不能受损；快速连续原生快捷键、菜单唤出／释放／取消不丢失、不重复、不额外等待。对比原生钩子处理P50／P95／最大值、检测／切换生效时间与实体按键延迟，三种范围分开报告。

这份评估不是功能验收。完整输入状态覆盖及真实切换／恢复尚未测试，自动ENG条目继续保持未完成。

2026-10-16：当前146／UXP18新增的是统一后台诊断，读取已有缓存、观测耗时和受限加载日志，不运行创建／修改文档的开发基准；本报告145及更早的时序数据保留原受测版本。图层读取下一阶段优化、自动ENG与跨机稳定性没有因检测整合而标为通过。
