# PS 临时 IME：当前实现、验证范围及历史评估

## 270：手动切中文后的重新保护

269中仍有两处缺口：策略把手动重新开启IME记为持续让行，直到下一轮真实输入；原生租约只持有旧TSF compartment指针，输入法切换后当前上下文或实际KEYBOARD_DISABLED值可能已改变。用户2026-10-26明确要求手动选中文后仍保护PS快捷键，此处保留用户选择的HKL／输入法，取消“直到下一轮编辑都停用保护”的规则。

非输入区域在确认原保护已恢复后重新核验当前状态并建立独立新租约。布局变化时重新读取工具状态；仍未确认的原生请求不清除、不重发。原生保留当前ITfContext的COM身份，检查实际禁用值；IMM重新关联、TSF值被重置或上下文更换时，续约／看门狗恢复旧租约，后台重新核验。状态查询只读，不在诊断中执行恢复；当前存在活动TSF上下文时必须匹配COM身份；解除IMM关联后，PS可能暂时没有活动TSF上下文，此时仍保留并读取原TSF的禁用值，不能丢掉这一层保护。新上下文出现或禁用值被重置时才结束旧租约并重新核验。WM_INPUTLANGCHANGE也触发原上下文恢复，但不能仅依赖它，因为[微软明确说明IME配置变化不一定发送该消息](https://learn.microsoft.com/en-us/windows/win32/winmsg/wm-inputlangchange)。

进入文字／重命名／数值／查找输入、未知、失焦、暂停或租约过期时继续恢复，只操作自己持有的PS上下文。新组件在原PS进程退出前被固定，更新需保存最新分层备份、正常重启PS；不强制结束进程或切英文布局。

666项低CPU完整回归和27项输入专项通过；原生低CPU／正常夹具覆盖真实IMM重新关联、真实TSF值重置、同一HWND更换TSF上下文、语言变化通知、原值恢复、无关新上下文保持、nonce、输入／失焦及超时。初版时序／焦点夹具失败与逐命令追踪保留，正式夹具通过AssociateFocus绑定真实窗口与TSF文档，未绕过产品前台条件。最终原生查询保持只读。证据.runtime/input270-native-tsf-low.log、input270-native-tsf-normal.log、input270-trace/test.log、tests270-final-low.log。

低CPU第一次PS原生命令未取得可信确认，保留未知；将共享命令应答上限从200ms改为1000ms，不添加固定等待，收到即返回。补充原生错误码诊断；新启动中观察到1460读超时但没有修改pending，不能把读超时当作修改成功。旧修改未知依用户全局授权归档，保存最新分层副本、正常退出服务／PS并用原进程句柄确认退出后才释放槽位；原请求未重发、未记成功或恢复。未完成测试的空白自建文档也保留了备份与仅跳过恢复它的审计，原稿已恢复。证据.runtime/recovery270ime/ime-unknown-normal-exit、owned-fixture-audit.json、eng270-new-startup-status.json。原200ms请求没有可比成功完成时间，不计算提速率。

Computer Use刷新返回的PS窗口后仍连续两次报“window id ... no longer belongs to ...; current owner is ...”，两处owner文本相同；没有发送按键，未把接口状态读回当作实体中文切换／首字母验收。初始自建文档未经编辑已关闭，原稿保留，见.runtime/eng270-baseline-target.json。异步识别仍有首键竞争边界；本轮是恢复保护的功能修复，没有可比实体按键延迟基线，不声明提速。实际270／UXP75和PS中加载的DLL哈希已核验一致。PS24.0.1低CPU真实35（IMM和TSF均保护）→21（恢复）→35（无需按键或编辑即重新保护）、查找面板打开恢复21、中文HKL0x08040804不变通过，原稿／配置／资源保持。初次IMM先解绑使实际PS只返回3的报告保留；改为先保存并禁用TSF、再解绑IMM，合法暂时无TSF焦点时继续检查原值，最终低CPU35通过。普通组已取得35和恢复21，但随后真实焦点离开PS而停验，未记为重新保护通过；额外菜单关闭后焦点切离也未计通过，没有连续抢焦点。证据.runtime/runtime270-verified.json、eng270-tsf-foreground-refused.json、eng270-imm-only-before.json、eng270-low-after-close-foreground-refused.json和eng270-low-live.json。


## 264：PS线程内禁用输入上下文

用户再次提供了快捷键触发中文候选栏的截图。261只有默认IME窗口的开关控制；264改为当前PS线程内的原生辅助组件，临时解除窗口IMM关联，并对当前TSF编辑上下文设置KEYBOARD_DISABLED。原键盘布局、输入法配置和转换模式不切换。组件只在经过进程、线程、焦点、UIA和工具状态核验后启用，不在低级键盘钩子里做PS查询。

原上下文／TSF原值保留在PS线程内。点击、焦点变化、编辑意图、离开PS或1.5秒续约失效时恢复；后台仅能续约自己持有且身份／布局／焦点未变的关联。没有活跃服务时，看门狗恢复并撤销控制窗口。只有同一PS进程和正确nonce的控制应答才能结清记录；明确拒绝单独归档，超时不冒充拒绝或成功。旧布局和旧开关记录只作恢复兼容；旧unknown仍保护，不能用重启清除。DLL在PS进程退出前保持有效，必要的版本缓存位于应用数据input-context目录；更换DLL实现需正常重启PS。

### 实测和限制

最终实际入口0.4.264／UXP0.3.71、PS24.0.1：低CPU和正常各一次，原生状态35（自有租约、IMM解除、TSF已禁用）到21（原上下文恢复），HKL始终0x08040804。查找输入窗口可见，历史／原稿／选择不变；实际PS加载DLL的SHA与发行资源一致。首轮200ms只读查询超时已保留，新的独立批次以1000ms只读等待上限完成；没有重发未知修改。独立原生夹具另覆盖错误nonce、真实TSF原值读回、鼠标／焦点恢复与租约过期。

Computer Use在PS重启后仍报相同窗口所有者校验错误，未发送实体键盘。上述是PS接口及原生读回，不能证明实体A／B、拼音首字、候选点击、快速重命名／数值、全部面板、其他输入法和原低配均已通过。本轮是功能修复，没有可比实体按键延迟基线，不声明提速。

文本实际入口另完成两配置12项操作及面板关闭后自动重新禁用，无键盘活动。普通Caps仍因真实鼠标范围保护未通过，不把文本工具面板结果冒充普通Caps验收。最终ENG证据.runtime/eng264-final-live.json；文本记录.runtime/text264-live/report.json。原陈旧前台采样失败保留，独立最终批次使用新鲜实际PS焦点。

### 菜单与忙碌结束的恢复

旧策略在非激活Caps菜单关闭或任务忙碌结束后，焦点和按键序号可能完全未变；此前同一意图已使用，因而即使新鲜工具状态再次就绪也不重新启用保护。修复仅在真实阻塞状态切换时轮换观察回合，并完整重验输入／工具状态；UIA失联本身不会轮换或自主往返。隔离生产策略复现旧菜单关闭失败，新回归覆盖菜单关闭和已知忙碌结束、零按键自动恢复；实际PS复核单独记录。

### 读取发布边界

真实事务后发现新input-tool-pending身份已保存，而input-tool-request.json仍是上一条，固定.tmp仍含新身份。原atomic_json对UXP文件占用没有发布重试，失败会留下等待不存在宿主结果的读取槽位。修复复用已有250ms有界原子发布重试，同一次发布保持ID／期限／字节不变；新本地记录区分prepared与published，线上协议仍为schema1。只有明确的发布前异常且失败归档成功后，才释放该未发布身份；发布成功后本地状态落盘失败、进程崩溃、旧格式或缺少可信结果时继续保留未知，不重新发布。

迟到结果仅只读核对原ID／会话／token／终态；已知失鲜／失败结清后，可以独立观察当前状态，无需先牺牲一次快捷键。用户已明确要求将这类只读观察的完整归档和槽位释放写入全局，C:/Users/mianx/.codex/AGENTS.md已落地。真实原未知ee6afd89811aa2016080c084905ae00f已在旧生产者正常退出后，完整归档并逐文件核验，再释放读取槽位，仍为未知、未重发，不改成成功；此前8282413f记录继续保持。原195及263归档记录不变。

Windows实际共享占用测试（低CPU／正常）均通过：持续无删除共享句柄使发布明确失败并完成未发布归档，当前读取槽位未残留；120ms占用分别经历22／23次相同字节的原子重命名尝试后发布成功，实际PS返回工具状态。测试没有重启PS或修改文档，资源及服务正常恢复。证据.runtime/tool264-publication-live/report.json。

用户进一步授权任意应用前台均可通过接口测试隔离PS文档，已写入全局；共享host_scope改为核验唯一PS的进程创建身份，退出／PID重用仍停止。产品快捷键与IME的PS前台限制保持。

构建：先运行tools/build-input-context.ps1，再运行tools/test-input-context.ps1和菜单构建；PyInstaller／发行打包同时校验InputContext.dll。API依据：[TF_GetThreadMgr](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-tf_getthreadmgr)、[Activate的配对要求](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfthreadmgr-activate)、[Compartment原值](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfcompartment-setvalue)、[输入上下文关联](https://learn.microsoft.com/en-us/windows/win32/api/imm/nf-imm-immassociatecontext)。

证据：.runtime/eng264-live-before-publication-fix.json、eng264-live-first-read-timeout.json、tool264-state.json、text264-live/report.json、recovery264reload及对应构建／回归日志。以下261记录为历史，不作为264实体键盘验收。


## 261：保持中文输入法的临时 IME 关闭／恢复（2026-10-25）

261 将生产入口改为 InputMethod：保持当前中文输入法及 HKL，仅关闭已确认 PS 非输入区域所属 IME 的 open 状态；明确输入、未知状态、菜单输入、产品暂停或离开 PS 时，只恢复本功能关闭过的原上下文。没有新增布局切换请求、US 布局依赖、全局设置或第三方依赖。旧 InputLanguage 仅供旧记录恢复兼容，不再由 Desktop 启动其切换工作线程。

沿用焦点、UIA 正向分类、独立工具读取、忙碌及键鼠保护，钩子不做宿主查询或 IME 调用。发送前再次校验进程创建时间、线程、焦点、原布局、IME 窗口及 open 状态；请求先落盘，读回后才确认。新的 input-method-owned.json 与旧布局记录隔离；未知不重发，手动选择不覆盖，已退出进程的确认记录先归档。关闭时只恢复本功能的已确认修改，不补发未知请求。

机制使用 [ImmGetDefaultIMEWnd](https://learn.microsoft.com/en-us/windows/win32/api/imm/nf-imm-immgetdefaultimewnd) 所属默认 IME 窗口及同步 WM_IME_CONTROL 的 open 状态控制；实际 PS 验证 PostMessage 未改变状态，保留该失败探测，改用有界 SendMessageTimeout。它是临时关闭输入状态，不是卸载或切换输入法。没有向其他应用发送 IME 控制。

真实查找面板发现：附着输入队列会让 PS 的 GUIThreadInfo.focus 返回 MenuHost 的 HWND。旧读回因此误认为没有 PS 上下文，恢复已执行但不能确认。修复后仅回到同一原 PS 线程的已验证窗口读取原 IME；不会读取或修改菜单／其他应用的上下文。原恢复 pending 在更新后依据同一请求及真实 open=1 结清，restore_requests=0，没有重发。第一轮暂停、第二轮失败和原收据均保留。

最终 621 项低 CPU 回归（64.194s）、60 项正常专项（6.190s）、原生完整矩阵、冻结启动／重启及嵌入资源一致性通过。PS24.0.1 实际261入口低 CPU／正常各完成一次 open 1→0→1，HKL 始终为中文 0x08040804；原生查找面板可见且输入标志有效，关闭不改测试文档内容／历史。另一次离开 PS 后恢复读回通过，Chrome 的中文 HKL 与 open 状态前后相同；计算机控制随后因无法可靠确认浏览器 URL 安全停止，不再发送桌面输入。这不是完整跨应用实体输入验收。

初始旧260确认记录已恢复中文布局，两处旧布局记录均无 owned／pending。原 ENG260 隔离文档已收尾；261 自建文档 ID67 关闭、原 gradientTool 和原文档数量0恢复，CPU资源恢复。实际运行 EXE、dist、原生菜单／热键、UXP68与源资源一致，配置与195历史未知记录保持；当前无 pending。

这是功能路线修正，无可比成功完成时间，不宣称性能提升。观察到实际入口关闭确认耗时低 CPU 337.879ms、正常202.882ms，各1次；仅是 COM 激活至状态读回的阶段样本，不是实体键到屏幕延迟，不计算提升比例。首次失败尝试观察337.462ms和489.594ms，分别因面板焦点变化和上述读回缺陷停止，保留而不混入最终成功样本。未覆盖冷启动／长时间闲置／持续操作性能。

尚未验收：实体 A、拼音首字／候选、快速文字编辑／重命名／数值、所有 PS 面板与第三方输入法、Win10／原低配及其他 PS。此前 PS 窗口绑定失败及这轮 Computer Use 安全停止，均不能以窗口消息或状态读回替代实体输入。未知区域保持输入保护，因此不能承诺每个首键都及时避开 IME。

证据：.runtime/ime261/{initial,installed,open-close-send-probe,live-first-stopped,pre-focus-fix-journal,live,chrome-before,cross-app-disable}.json、legacy-ime-layout-cleanup.json、runtime261-verified.json、tests261-low.log、ime261-normal.log、native261-low.log、build261.log、smoke261.log及caps261-candidate.json。未公开260保持历史候选，不把原失败批次改为通过。

## 用户目标修正（历史记录，2026-10-25）

用户明确说明：要求保留当前中文输入法，PS非输入区域临时禁用IME，进入输入场景恢复；不是切换英文键盘布局。下文259／260的切HKL路线及读回记录只是旧实现历史，不能作为临时禁用已交付的证据。已正常退出旧服务，停止追加旧路线测试，原确认ownership／未恢复布局及失败批次保持记录；没有清除未知或把未恢复改为成功。

临时禁用方案尚未实现／验收。原生窗口绑定两次报“所有者不符”（显示的所有者文字相同），应用控制入口另报0x80070020，未发送桌面按键。新PS低CPU旧路线批次只完成切换和路径选择，随后前台变化停止：两次切换／一次恢复，剩余布局恢复和自建ENG260文档收尾保留待办。报告见.runtime/eng260-restart/partial-new-ps.json和eng260-live/1792914764346911700/report.json。不能将此批次记为完整通过，也不发布260为用户所需的临时禁用版本。

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
