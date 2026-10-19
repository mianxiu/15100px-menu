165／UXP32：旧版独立预览已接入并按用户要求发布，实际PS事务通过，实体画布待验收。详见[Wiki](https://github.com/mianxiu/15100px-menu/wiki/Legacy-preview)。

204／UXP44：修复PS24.0.0被实时预览版本条件排除的问题。该版本已可安装，但旧插件仅对24.0.1及之后的24.0.x报告独立预览能力，后台也有相同门槛，导致颜色／羽化不能实时生效。现将独立预览路径扩展到24.0.0，必须实际加载UXP44并报告对应能力；旧UXP43在24.0.0仍不会被强行启用。23.x仍保持兼容草稿，24.1+仍须实际提供官方重绘API，不在未知结果后改走另一通道。

其他电脑请先保存文档，正常关闭PS，在新版后台安装／更新内置UXP44，再手动启动PS，确认后台实际加载0.3.44。只换EXE或只降低安装清单门槛不能生效。完整安装会同步本插件的共享加载登记，包括版本、名称和23.3.0的安装下限，保留其他登记。打开后台及安装后不自动启动PS。

204本机已构建并切换实际入口，PS24.0.1已正常重启加载UXP44。472项Python、双逻辑处理器／Below Normal的100项预览专项、21套脚本及冻结EXE启动／重启检查通过。本机三轮真实接口事务（低CPU确认、正常确认、低CPU取消）均等待两帧新值读回与app.refresh返回；同一目标、一次确认／一次撤销及取消恢复颜色／羽化／密度通过，资源恢复。原文档分层备份并恢复副本，源文件、配置和旧未知保留；真实后台在PS关闭时观察8秒未自动启动，手动启动一次成功。Win10 19045.3803／PS24.0.0 20221013.r.59／32GB故障机尚待复测，实体鼠标／Caps与画布目视未验；模拟版本分流不等于该机验收。无新增公开Release。

198／UXP43：依据Adobe官方文档，将插件声明、安装／启动检查、运行心跳校验和版本自检的最低Photoshop版本统一为 **23.3.0（Photoshop 2022，UXP 6.0）**。这是文档与代码审计确定的安装／运行准入门槛，不代表23.3已通过本项目实机验收；当前真实宿主验收仍为PS24.0.1。

| 项目实际依赖 | Adobe最低版本与项目处理 |
| --- | --- |
| Manifest v5与插件文件权限 | [PS23.3.0／UXP6.0](https://developer.adobe.com/photoshop/uxp/2022/guides/uxp-guide/uxp-misc/manifest-v5/)，决定本次总体声明下限。 |
| 启动时驻留 `loadEvent: startup` | [PS23.1+](https://developer.adobe.com/photoshop/uxp/2022/guides/uxp-guide/uxp-misc/manifest-v4/photoshop-manifest/)，继续保留apiVersion 2。 |
| 模态交互与一次撤销 | [交互模式PS23.3](https://developer.adobe.com/photoshop/uxp/2022/ps-reference/media/executeasmodal/)；[历史暂停／恢复PS23.0](https://developer.adobe.com/photoshop/uxp/2022/ps-reference/objects/options/executioncontext/)。不削减回滚、输入、忙碌拒绝和未知不重发保护。 |
| PS面板字体偏好 | [DOM读取PS24.0+](https://developer.adobe.com/photoshop/uxp/2022/ps-reference/classes/preferences/preferencesinterface/)；已有异常保护保留，23.x缺少此DOM时沿用小字号，主题仍走原只读get，不新增PS查询。 |
| 官方实时重绘 | [core.redrawDocument从PS24.1起](https://developer.adobe.com/photoshop/uxp/2022/ps-reference/media/photoshopcore/)，仍同时检查API存在，不随安装门槛降低。 |

PS23.3～23.x可通过安装准入检查，尚未实机验收，缺少预览能力时保留兼容草稿／确认提交。204起，24.0.0≤PS<24.1可在新UXP明确报告能力时走独立预览；24.0.0需UXP44，24.0.1已有路径保留。24.1+检查实际官方API；安装准入与各版本完整功能验收分别记录，24.0.0仍待对应实机验收。

已有UXP43如果只有最低版本声明不同、脚本与凭据和自有文件核验一致，可备份后仅迁移manifest及所有权收据；不改main.js／labels.js／凭据，不重启PS。自动跟随在忙碌或原结果待核对时等待，外部改动或其他清单差异拒绝热迁移；真正的脚本更新仍要求正常关闭PS。主程序版本为198，插件执行代码版本继续为43。

198本机交付：468项Python回归（含23.3边界、旧清单迁移、阻塞／外部改动拒绝和失败恢复）、只读字体缺失模拟及冻结EXE启动／重启通过。已切换实际198；EXE／Windows文件版本／嵌入资源及菜单、热键匹配。已安装清单和收据均为23.3.0；main.js、labels.js及凭据字节／时间戳、共享加载索引、PS会话、用户1.psd及历史未知记录保持。通过198门槛完成一次本机PS24.0.1真实只读UXP检查，无文档修改或新待核对任务。原生与前端未改，沿用197验证，未重复四主题。23.3～24.0.0、UXP6.0和其他实机仍未验，不将文档或模拟边界等同兼容通过；本轮未新增Release。首次EXE替换遇Windows锁，核对旧进程全部退出和旧文件完整后，从替换处完成更新，未重发退出或宿主请求。

以下为历史版本与验收记录，原24.0.1声明下限已由198调整。

# Photoshop 快捷菜单 v0.3.31 — UXP

以下为164候选的历史记录（当前165实现与验证见上方Wiki）：当时本目录为PhotoshopMenu v0.4.164／UXP0.3.31候选执行端源码，已构建并切换实际入口，内置／安装／加载UXP31已核验；正式Release仍159。最低PS24.0.1，仅代表可安装和基础操作范围，不代表全版本实时预览验收。31移除UXP事务内嵌套JSX刷新：有官方API的24.1+走实时通道，旧版暂用本地草稿、确认单次提交。旧PS有ExtendScript重绘能力，独立旧版实时执行路径尚未实现，不能把草稿保护视为需求完成。原未知请求保留，旧空PS经明确授权结束，新会话已正常启动及退出；实机预览测试因界面工具独立故障暂停，见[验证状态](../../docs/MASK-PREVIEW.md)。

其他电脑需分别核对磁盘安装与宿主心跳；安装成功不代表PS必然识别。147针对已有用户索引遗漏增加登记维护，本机PS24.0.1复现与恢复通过，故障Win10／PS25.5仍待复测，见[加载修复](../../docs/UXP-LOADING.md)。

0.3.19只调整selectionContext的同级对象构造：新鲜集合按需读取，本次快照内复用，小列表／多数选择原路径。全部能力字段、成员及最终身份校验保留，轮询／刷新／到期策略不变，capture及后续事务代码保持。真实同宿主520次旧／新字段一致与最终148生产读取、自然刷新、创建／选择／调色回归通过；详见[性能范围](../../PERFORMANCE.md)。临时测试插件已经移除，生产不增加任意脚本入口。

0.3.20新增可选mask草稿（feather 0–1000px、density 0–100%），仅在合格矢量形状读取官方DOM属性，不读独立像素蒙版。字段计入revision、写前强制读新状态；仅改蒙版不写shapeStyle，与改色共用一个历史事务并读回，失败回滚、未知结果不重发。旧客户端不带mask时保持原蒙版；后台在向19及更旧插件发布含mask修改前拒绝。普通填充不读取或显示此字段，原颜色／路径／选择保护保持。真实PS边界／读回／一次撤销和旧mask revision拒绝通过，实体滑条另列未验收。

0.3.21增加有界位置提示，每次在新鲜同级集合用精确ID核验，失效回退原扫描。只存标量位置，不缓存类型、锁定、能力或旧DOM对象，不改变轮询和capture后的事务；首次未知位置仍可能扫描。用户使用与测量范围见[Wiki](https://github.com/mianxiu/15100px-menu/wiki/Layer-performance)。

0.3.22为菜单／后台只读入口新增selectionContextFresh：只有大列表未命中位置才有界读取原生ID，按父组生成候选位置，仍由新鲜DOM核验与重读能力。异步身份变化拒绝，失败／超范围回退，暖路径不加查询；capture及其后写入事务保持。使用与测量见[Wiki](https://github.com/mianxiu/15100px-menu/wiki/Layer-performance)。

0.3.27／28的刷新尝试经用户目视确认仍不能随拖动更新。0.3.29的旧版固定刷新脚本曾目视生效，但连续低CPU测试失联，尚无匹配终态。0.3.30保留实时预览／取消恢复／一次历史，减少拖动中无关读取，限定本地控制文件等待并复用未返回读取，记录原请求执行阶段，紧邻颜色写入核对原文档／图层身份并读回；不兼容的ID setter试验已回滚并撤回，保留原生contentLayer写法；保护修订还在模态外保留不确定状态，避免真实PS重建异常时丢掉未知标记；提交／回滚结果异常不重复resumeHistory，错误回滚也核对原值。347后台及49组预览模拟通过，完整实机低配验证未完成。旧版刷新调用的稳定性不能保证，具体状态见[Wiki](https://github.com/mianxiu/15100px-menu/wiki/Mask-preview)。

## 当前命令与保护

本地PluginData文件协议支持固定的inspect、capture、set_label、new_document请求，不提供任意脚本／描述符入口或网络权限。菜单与快捷键修改通过UXP执行，忙碌拒绝新交互，不排队；已接受／最终收据持久化，未知结果只核对原请求，不重发、不自动回退COM。修改前重新校验会话／文档／活动层／选择／到期及能力，完成反馈前准备并同步新选择。

- 标签八色／清除、组内或相邻选择、置顶／置底和上移／下移。移动快捷键已移除，使用上方图文按钮。
- Caps+C／V复制／粘贴样式，Caps+F原生样式；Caps+W／S单选相邻，Shift组合追加多选（0.3.16起）。
- F5将当前选择转换智能对象（0.3.18起），核对类型、父组、其他层顺序与新选择，单个已有智能对象不嵌套；一次撤销遵循PS原生历史。
- 空白／纯色／调整层在同父组紧邻活动层上方原生创建；选中组时在组内顶部。默认命名、原层保留、原生位置／树／类型读回和同一历史事务保持，不事后移动掩盖位置异常。
- 形状和普通纯色／渐变／图案填充在RGB8／16位、单选未锁定范围内编辑。具备官方API时颜色面板在同一个历史事务实时预览，取消恢复；旧版暂为兼容草稿、取消不写PS。两者均在Caps松键或固定后再次Caps确认，中心／空白、Esc及右键取消。渐变是连续颜色条和可拖动色标。

## 当前读取与验收边界

0.3.17起菜单基础能力先于可选颜色数据发布；后台不持续读取矢量颜色或图案目录，基础DOM读取按耗时限频。菜单只读请求10秒，但快照新鲜度、请求ID／菜单代次／会话／目标与修改前核验不放宽。单次快照复用属性、父组和同级列表，不跨请求复用旧目标。当前未用事件通知替代有界轮询。

145历史转换验收为300后台、13前端、原生／最终EXE检查及真实PS24.0.1转换／撤销通过；实体Caps／F5、i5／PS24.2连续使用、Win10／PS25.5加载未闭环。最新4／100图层基础识别中位48.5／280ms，仅为基线，进一步算法优化尚未实现。见[性能](../../PERFORMANCE.md)、[读取实验](../../docs/READ-STRATEGIES.md)、[待办](../../TODO.md)。

## 部署与诊断

通过主程序后台安装、跟随更新、导入／导出、回退和卸载；更换前正常关闭PS，随后核对实际加载版本。ZIP只含manifest.json、main.js、labels.js、package.json；不发布probe-config.js或用户uxp-config.json。本地External部署和启动／重启恢复在本机验证，不承诺全部宿主和全新用户环境均可用。

安装／更新步骤见[离线管理](../../OFFLINE-INSTALL.md)。PS菜单完全无插件时使用最新源码[只读加载采集](../../tools/inspect-uxp.ps1)；有菜单但无连接可先用“检查连接”。旧实验客户端不得与生产请求并发运行。

<details>
<summary>历史实现与实验记录（以下旧版本、创建位置、输入方式及未完状态均为当时记录）</summary>

## 0.3.10及更早历史记录

当前为PhotoshopMenu v0.4.120内置的生产写入端，启动PS自动加载；所有修改经本机文件协议与UXP执行，不联网、不回退COM、不重发未知结果。普通及组内层上方直接原生创建，选中组时在组内顶部；PS默认编号、原层保留、实时目标检查与同一历史事务一次撤销均保留，创建后在完成前同步精确新选择。

0.3.10在单次快照内复用属性／父组／兄弟列表，并在同modal准备创建后的选择快照；缓存不跨任务，结束后核对身份。读取实验0.3.11仅位于tools/fixtures/read-strategies-0.3.11，不嵌入发行包。完整连续创建与特殊图层／数量测试未证明替换get／multiGet或事件兜底更快，生产保持当前方案。见[实测报告](../../docs/READ-STRATEGIES.md)。

以下为0.3.7及更早实现的历史记录；旧“组外空白层”规则已被上方当前组内原生规则取代。

Plugin 0.3.7 is the production write endpoint for PhotoshopMenu 0.4.112. It loads at Photoshop startup and handles menu labels, clear, selection, sorting and layer creation through authenticated local PluginData files, executeAsModal, target checks and result readback. COM remains read-only for theme/font/connection status. There is no network permission or automatic COM write fallback.

0.3.7: fill and adjustment layers follow native Photoshop insertion: immediately above the frozen active normal layer, within the same parent; selecting a group creates inside its top. The disposable layer that protects an original empty pixel layer is positioned before make, then cleaned up before final position/type/count/order verification. Default names are generated by Photoshop for fill, adjustment and grouping. All creation/positioning shares one undoable history entry; errors roll back. The existing blank-layer rule stays above a selected group, outside it. Real installed-UXP tests compare 35 fill/adjustment cases with native Photoshop commands and regress eight blank-layer cases, including undo and stale-target rejection; physical menu clicks remain separately pending.

The main PhotoshopMenu.exe embeds manifest/main/labels and its backend Plugin Management page installs, enables/disables execution, imports/exports offline updates, rolls back and uninstalls UXP. Build the unified EXE ZIP with tools/build-backend-package.py; the separate OfflineSetup is historical deployment only. It includes the main EXE and manifest/main/labels only, generating or reusing the user's token locally. Never distribute probe-config.js or user uxp-config.json. See OFFLINE-INSTALL.md for install/update/rollback/uninstall and the physical validation limits, and PERFORMANCE.md for the actual COM/UXP comparison. Declared minimum Photoshop is 23.3.0 (UXP 6.0); PS23.x is not physically verified. This floor is enforced by installer metadata, plugin manifest and runtime heartbeat checks, with no upper bound. The physical validation scope remains 24.0.1 / UXP 6.3.3; later-version installation eligibility is not compatibility acceptance. The original plugin ID/name is retained for installation identity.

The sections below are historical experiment notes, not current production status. Experimental clients must not run concurrently with the production transport.

## Shape paint (UXP 0.3.12)

The fixed `shape.paint` command edits a single unlocked vector shape in RGB 8/16-bit documents. Metadata reads four targeted properties and caches them for 500 ms; non-shape layers retain the original DOM-only observation. Preset classes accept the host's pattern class aliases. No status JSX or network calls are introduced.

The native picker edits a local draft. Tab switches solid/gradient/pattern. Fill/stroke, RGB/Hex, black/white, existing gradient stops (2–32), loaded local pattern names, stroke width and swapping are supported. Hold release inside the picker submits once; a pinned picker submits on the next CapsLock. Centre/blank release, Esc and right click discard. Existing radial buttons execute their own actions.

Execution checks the captured session/document/selection and paint revision again inside one modal/history transaction. One shapeStyle set is read back, checking paint, enabled flags, width and unchanged layer identity/order. Failure rolls back; an unconfirmed rollback remains unknown and cannot be replayed. Independent live tests verify vector path streams and one undo. Physical key/mouse acceptance is recorded separately in TODO.md.

## Commands and safeguards

The token-authenticated plugin-data transport supports inspect, capture, and set_label only; no network, arbitrary JavaScript, or Adobe installer is used. Capture returns the plugin session, document ID, active layer ID and selected layer IDs. Label execution rechecks these within executeAsModal, validates expiry/cancellation, suspends history, sets the selected layers, reads back each color, and rolls back the history transaction on failure. Allowed colors match the existing eight Photoshop 24 labels including none. Requests are consumed before execution to prevent automatic replay within a session; old-session targets are rejected after restart.

The experimental Python client rejects concurrent calls within the same client and stops after an unknown result. It does not provide production-wide coordination with the existing COM executor. Do not run multiple clients, the old observer, or production operations concurrently during a write test. Production busy feedback, cross-process admission, cancel UI, inherited group-color explanations and full menu integration remain outstanding.

Run node tools/test-uxp-file-probe.cjs and node tools/test-uxp-labels.cjs for simulation. Run Scripts/python.exe tools/verify-uxp-labels.py only with Photoshop ready and the production service idle. It creates its own scratch document, executes eight label writes through UXP, independently reads them through COM, tests changed-target rejection, then closes its own scratch document and restores the previous active document. Never interpret simulated results as physical acceptance.

Deployment is an experimental local copy to %APPDATA%/Adobe/UXP/Plugins/External/com.15100px.menu.offline-probe_PS. Deployed manifest/main/labels/token hashes were checked. The old version is backed up in .runtime/uxp-0.1.3-before-labels. Token files and local archives must never be published. Official CCX installation has not been validated.

Automated Start-Process, Shell.Application, and Explorer launches failed to load the new UXP session with the CCD issue unresolved. Previously, direct user launch succeeded. Do not keep repeating the failed automatic launch, alter firewall rules, Adobe binaries, account data, or user preferences. The five-minute offline observer has been stopped at the user's request; whole-machine disconnection is not required.

Physical update: 0.2.0 has now passed real single-layer eight-color/clear, two-layer blue/clear, three target rejection cases, and expired-request rejection followed by a successful inspect. All scratch documents were cleaned up; original document restored. Evidence: .runtime/uxp-labels-physical-verification.json. Production integration and automatic startup remain incomplete.


Production update: plugin 0.3.0 is now used by PhotoshopMenu v0.4.69 for all menu writes. Production transport is backend/uxp_bridge.py and stores the local token in the user PhotoshopMenu/uxp-config.json. The legacy experimental client must not run alongside production requests. Label, group selection and root/group sorting passed real bridge tests; actual EXE action.execute label/clear passed. Theme/font/connection reads still use COM. No automatic COM write fallback. Unknown results keep the service busy. Whole-machine disconnection is not required under the user's existing outbound block.

0.3.1: managed Chinese/English display names, stable plugin and command IDs, runtime manifest metadata in the heartbeat. Backend controls the language when installing or applying the name while Photoshop is closed; no network permission added. Production backend v0.4.74.

Backend v0.4.83 displays the manifest version in the Chinese and English plugin names. Name application changes only the manifest while Photoshop is closed and preserves IDs, code, credentials and enable state.

UXP 0.3.6: blank-layer creation uses the native make command without an explicit name. Placement is verified immediately above the frozen active layer in the same parent, corrected only when necessary, and committed as one undoable history entry. A selected group receives a sibling above itself; a selected group child receives a sibling within that group. tools/verify-blank-layer.py validates eight disposable real Photoshop cases against native naming plus stale-target rejection.

## 0.3.13 形状与填充

形状层保持填充／描边及类型切换；普通纯色、渐变、图案填充层支持编辑自身内容，保持类型且不修改描边。按原生填充描述符写入，一次历史事务，写后核对类型／身份／顺序，失败回滚；未知结果禁止重发。

</details>

146历史交付仅整合后台诊断，UXP执行代码与0.3.18保持一致；146的305后台、14前端及实际诊断接口结果见根README和TODO，不把后台检测通过当作插件故障修复。

147只修改后台加载登记生命周期，插件执行代码与0.3.18保持一致；实际自动／手动修复、重启加载及标签事务验收见根README／TODO。索引原始恢复副本保存在私有用户备份，不随导出插件包发布。

0.3.23新增创建前整树分流：32节点内DOM，大树有界multiGet并校验完整性／前缀，失败回退；写后DOM结构、实时目标和一次撤销保持。见[完整事务与限制](../../docs/CREATION-TREES.md)。

0.3.24新增矢量蒙版实时预览：一个持久化请求／一个历史事务，合并最新滑条值，确认单次撤销，取消读回原值；4秒租约与最终结果核对保护。0.3.25扩展到填充／描边及渐变色标，旧插件拒绝新预览命令。操作与验证范围见[实时预览](../../docs/MASK-PREVIEW.md)。

0.3.26修复带矢量蒙版目标实时填充颜色触发“Set不可用”：统一使用shapeStyle，仅普通无矢量蒙版填充层使用自身原生类型setter。旧请求等待匹配终态，不重发或清busy；UI颜色／羽化面板拆分不增加UXP事务。
