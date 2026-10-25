# 自动 ENG：当前实现、验证范围及历史评估

## 260候选：PS重启后的旧ENG记录（2026-10-25）

259已实现并公开自动ENG，但本轮继续TODO时发现一个真实重启边界：PS及服务均已退出，input-language-owned.json仍有10804旧进程的已确认英文切换记录、pending=null。旧策略遇到新进程身份时始终返回，因而新PS不能继续自动切换。保留原始记录并用259策略复现拒绝，没有向PS或系统布局发消息。

260只处理已确认的ownership：读取原PID的进程创建时间／退出状态，缺失PID还需特定错误及进程枚举共同证明；访问拒绝、查询失败、仍在运行或任何pending都不释放。先持久归档原记录和“不发送旧布局恢复”的原因，再清空当前已确认ownership；新PS仍需原有新鲜焦点／输入／工具校验。PID重用通过创建时间区分；不是把新窗口当成旧窗口恢复。

依据[Windows进程句柄与标识](https://learn.microsoft.com/en-us/windows/win32/procthread/process-handles-and-identifiers)、[GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes)及[GetExitCodeProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getexitcodeprocess)。完整未知请求继续保留、不重发；本轮不清UXP pending或195历史记录。归档或当前记录写入失败时保留内存ownership；不合法记录在进入关闭恢复逻辑前拒绝。

604项完整回归（低CPU58.611s）、正常43项专项、原生矩阵及冻结启动／重启通过。新增回归覆盖运行中／已退出／PID重用、查询拒绝／失败、归档写入失败、原请求未知、新工作线程启动及损坏记录不触发关闭恢复；自建短命Python进程自然退出的真实Windows核验通过，没有强制结束进程。此为重启功能修复，没有可比成功完成时间，不计算提速率。

实际入口260的首次启动已将原已确认记录完整归档，当前owned／pending为空，switch_requests／restore_requests为0；UXP文件仍68，配置和历史未知保持。当前没有运行中的PS；新PS启动及切换／恢复实测因Steam前台暂停，尚未发布260。公开下载仍259；不把归档检查标为新PS实机通过。

证据：.runtime/eng260-restart/before.json、configuration-before/input-language-owned.json、install.json、tests260-low.log、eng260-normal.log、caps260-candidate.json与smoke260.log。归档文件在实际用户数据目录，路径见install.json。先前split260-baseline只完成三组读取／预览零写入，后续按钮测试中断前未执行，继续保留待验。

## 259：实际切换／恢复与超时抖动修复

259／UXP0.3.68已构建并更新实际入口，PS无需为本轮259再次重启；正式下载状态集中见Wiki Versions。范围为整个PS前台可确认的非输入区域，不要求先点击画布。文字编辑、重命名、数值、搜索及未知状态继续保护；没有已安装美式英文时不切换。它不是系统全局默认输入法设置，也不保证焦点变化后第一枚实体字母已切换。

258实测首先完成无点击切换和路径工具检查，随后发现UI Automation返回0x80131505超时，状态未知触发安全恢复、查询恢复后又自主切ENG，产生抖动。该错误对应[微软UIA超时](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-error-codes)；查询等待由[IUIAutomation2.TransactionTimeout](https://learn.microsoft.com/en-us/windows/win32/api/uiautomationclient/nf-uiautomationclient-iuiautomation2-put_transactiontimeout)控制。

259将独立工作线程的连接／查询上限从100ms改为500ms，不在钩子内等待。未知引起的确认恢复保留已尝试意图，相同意图不会自主再次切ENG；新活动才允许重验。明确输入引起的恢复仍允许正常返回ENG。布局结果未知仍保留原身份、不重发，未把超时当作成功，也不复用失败的UIA元数据。

### 真实PS及实际入口证据

PS24.0.1隔离200px文档先低CPU（双逻辑处理器／Below Normal）、再正常配置，各完成无点击ENG、路径选择、直接选择、闲置文字工具和禁用恢复；每组4次读回确认切换／4次确认恢复，8次只读工具查询。文档选择／历史未变、临时文档关闭，原稿、原布局与资源恢复。正常组另静置2秒，无追加切换；实际259服务及原生事件链在低CPU下16次轮询、约4秒静置，无追加切换／恢复，最终布局仍英文。没有实体键鼠输入，不能将接口切换等同于实体A快捷键已验收。

595项Python回归在低CPU通过（59.958s），原生菜单／热键完整矩阵、正常34项专项、冻结EXE启动／重启和UIA加载通过。新增测试覆盖未知恢复不自循环、新活动重验，以及真实输入结束后仍可恢复ENG。实际入口、dist、原生进程及嵌入资源一致，配置、UXP／PS会话和195历史未知记录保持；本轮未重启PS、未创建额外发行回退包。

259低CPU查找实屏中文字符筛选／空结果／边界／关闭不改历史通过；正常组重开因焦点／取消隐藏而停止，未继续提交，原稿与资源及临时文档收尾通过。256／257同一原生文字控件的低CPU／正常查找证据保留；拆分面板和三档字号的完整PS实屏验收仍未完成。

### 时间与未验范围

从独立控制器线程启动到确认ENG：259低CPU204.106ms、正常247.085ms，各1样本；单样本中位／P95／最大均等于该值。258第一次低CPU934.347ms来自后来失败的批次，缺少相同完整操作与稳定样本，不能作为可比速度基线，未计算提升率。以上不含实体按键到屏幕延迟，也不代表冷启动／长闲置性能。本轮为稳定性修复；500ms是失败等待上限，不是固定延时，慢查询下检测／恢复可能更迟。

完整实体A、拼音首字／候选、快速文字编辑与重命名／Tab、数值／搜索、跨应用、三档完整PS面板、原低配／其他PS版本仍待验，未据此勾选广义ENG全部完成。电脑控制内核此前两次退出，未换用其他通用键鼠注入绕过。失败与拒绝记录保留。

证据：.runtime/tests259-low.log、eng259-normal.log、native259-low.log、smoke259.log、caps259-candidate.json、install259-verified.json、runtime259-verified.json、eng259-live/1792756352035703500/report.json、eng259-normal-live/1792756410941243800/report.json、eng259-runtime-idle/1792756454201486500/report.json、panel259-live/1792756495706987400/report.json。258失败记录eng258-live/1792755999863856300及零样本UIA探测保留，均不计完整通过。

## 258历史候选记录

### 当时状态：PS前台非输入区域

258／UXP0.3.68已切换实际入口，公开下载仍为254。目标是让整个PS的可确认非输入区域自动使用美式英文布局，减少A等原生快捷键被中文输入法占用；输入框、重命名、数值、搜索和文字编辑保留输入能力。无法确认的焦点不切换，不把没有caret当作安全证据。

UI Automation在独立MTA线程读取焦点控件元数据，不读取文字、值或名称。工作区通用容器还需core.getActiveTool的工具和isModal证据；独立只读邮箱不进入模态、不改文档、不占修改槽。钩子只转发焦点／字母活动，不查询、不吞键或补发。发送布局请求前再次核验身份／焦点／布局，读回后才确认，只恢复本功能更改的原布局；未知请求保留身份、不重发或COM回退。异步焦点到首键仍有竞态，不能承诺第一枚字母在任何时序下都已切换。

### 本轮实测发现与修复

- 真实pywin32返回线程／进程列表，旧比较按元组处理，导致合法PS焦点被误判未知。共享采样改为解构后逐项比较，新增列表／元组、异进程／线程和caret优先保护三项测试。
- PS24.0.1的core.getActiveTool实际字段为classId，Adobe参考写classID，旧候选因此返回可信失败。UXP68兼容两种格式，同时存在但不一致仍拒绝；错误只保留有界工具结构诊断。真实只读请求已返回gradientTool／isModal=false，未发送布局请求。
- 首次258包的心跳自报版本漏同步，加载核验拒绝；已修正并重新构建／切换，实际加载68。失败产物、原失败终态与恢复记录保留，没有伪造成功或重发原请求。

### 验证状态

593项Python回归在双逻辑处理器／Below Normal通过（56.881s），原生菜单／热键完整矩阵通过；最终修复的30项ENG／读取协议专项及UXP文件协议／版本一致性检查通过。冻结EXE启动／重启及UIA加载、后端源码／嵌入资源核对、实际入口／dist／原生组件／网页资源匹配通过。配置、195历史未知保护和原文件保持，重启前保存分层副本并核验恢复内容；历史栈不视为跨重启保留。

256、257实际服务的低CPU／正常两组查找通过：自动全结果、中文字符消息筛选3项、空结果、PS／工作区边界、实屏内容及关闭不改选择／历史。拆分第一次因新鲜文字快照未就绪被拒，补足快照等待后因PS前台条件失效被拒；未提交拆分修改，两次原稿／资源及临时文档收尾通过。它们不计为拆分实屏通过。

ENG隔离前台尝试分别遇到可信工具失败或Windows拒绝激活；未完成本轮切换／恢复验收。原请求已终态的只核对原记录，不重发；当前无修改／工具观察pending。最终258实际加载68并恢复原文档副本后，等待PS前台短批次；不反复抢焦点。

实体拼音首字／候选、重命名／Tab、数值／搜索、闲置文字工具／A切工具、跨应用及原低配／其他PS版本仍待验。Windows电脑控制内核两次退出（0x80070020），未用其他键鼠注入方式绕过。没有本轮可比完成时间，不宣称速度提升；阶段样本也不冒充实体按键延迟。

证据：.runtime/tests257-low.log、native257-low.log、eng257-normal.log、eng257-unit.log、caps258-candidate.json、smoke258.log、runtime258-verified.json、tool258-readonly/observed.json、tool257-original-terminal.json、recovery258breload、panel256-live、panel257-live、eng257-live及eng258-live。早期256自动测试与Windows三类自建控件UIA证据仍保留。

## 历史范围与评估

244／UXP0.3.63：已启用有限范围自动 ENG。仅 PS 前台、明确点击画布、确认非文字工具且焦点属于画布时，异步切到已安装的美式英文布局。没有标准 Edit／caret 不会单独成为切换依据；未知场景保持不动。T／Shift+T 原样交给 PS，同时取消旧画布意图。进入确认输入／文字工具时，仅恢复本功能此前更改的布局；手动切换后不覆盖用户选择。不修改全局输入法、PS快捷键或注册布局。

布局查询、工具确认、切换和读回均在独立工作线程，键盘钩子仅转发意图；每次明确画布意图最多两次只读工具查询，不按帧访问宿主。持久化原身份／布局及待核对请求，未确认不重发；退出或重启后只在同一前台PS身份及布局匹配时恢复。外部应用不切换，没有安装美式英文时不执行。原广义“所有非输入场景强制ENG”仍未完成。

验证：真实PS24.0.1隔离文档低CPU（双逻辑处理器／Below Normal）和正常配置各3次切换／恢复，全部核对真实线程布局、历史不变及原工具／布局／文档和CPU恢复；驱动为合成画布意图，不是实体按键。自建Windows窗口另12次布局往返确认；200次GUI状态／布局成对读取中位2.6微秒、P95 3.4、最大54.8，仅该对API成本。原失败及中止证据保留。

|配置／阶段|样本数|中位数ms|P95 ms|最大ms|
|---|---:|---:|---:|---:|
|低CPU切ENG|3|531.961|546.840|546.840|
|低CPU恢复|3|428.007|445.899|445.899|
|正常切ENG|3|545.369|551.610|551.610|
|正常恢复|3|405.372|425.136|425.136|

以上包含测试目标／历史独立读回，不代表实体首键延迟；N=3的P95按最近秩为最大值。旧版无可比成功实现，因此优化前→优化后为“无→上述新功能样本”，不计算绝对／百分比提速。原始样本：`.runtime/eng243-live/1792676683889629800/report.json`。首次中文字符、候选／组合输入、重命名、Tab连续重命名、自定义文字工具快捷键、冷启动／闲置与其他PS／硬件尚未完成实体矩阵，不能承诺首键必为英文或所有输入框均已识别。

## 历史记录

2026-10-22核对实际239／UXP0.3.61：仍未实现或启用自动ENG，也没有完成第二阶段只读输入状态观察。238的单独F搜索属于快捷键映射，不检测或改变键盘布局／IME；已有输入保护不等于完整识别重命名、候选词和组合输入。以下133测量仍为历史评估，不能作为238输入法功能验收。

2026-10-15；评估基于实际运行 v0.4.133／UXP 0.3.13。没有实现或启用自动切换，没有修改键盘布局、IME设置或PS文档。

2026-10-16同步：实际150／UXP20仍未启用自动ENG；只读观察作为后续评估，不因Caps意图或F5变更自动开启切换。本文133／UXP13测量为历史基线。

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

2026-10-16：146／UXP18当时新增的是统一后台诊断，读取已有缓存、观测耗时和受限加载日志，不运行创建／修改文档的开发基准；本报告145及更早的时序数据保留原受测版本。图层读取下一阶段优化、自动ENG与跨机稳定性没有因检测整合而标为通过。
