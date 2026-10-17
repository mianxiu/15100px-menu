# 目录与本地归档

2026-10-17同步：本轮159／UXP26独立面板与填充修复交付记录见下方；此前155为历史时点。源码、历史实验、当前发行物和本地资料分别存放；下面明确标为2026-10-12的整理数据属于历史时点。

| 路径 | 用途 |
| --- | --- |
| `tools/verify-diverse-layers.py`、`tools/benchmark-tree-snapshots.py`、`tools/fixtures/tree-snapshot-study` | 自建PS样本的类型／样式／智能对象／4K事务验证和只读整树算法研究；独立临时插件，不进入EXE或发行ZIP |
| `tools/benchmark-layer-snapshots.py`、`tools/fixtures/selection-context-0.3.18.cjs` | 新鲜生产读取测量、冻结旧算法语义对照；不随运行入口加载 |
| `tools/test-hotkey-opening.py` | 无输入钩子的生产输出队列时序对照；不代表实体按键到屏幕 |
| `main.py`、`start.ps1`、`build-exe.ps1` | 当前启动／构建入口 |
| `backend/`、`frontend/`、`native/`、`uxp/`、`jsx/` | 当前实现与内置资源 |
| `photoshop_action/` 与根目录 COM 兼容模块 | 后端仍引用的兼容代码 |
| `tools/`、`tests/` | 维护工具与自动回归 |
| `legacy/` | 早期独立实验，不属于当前运行入口 |
| `dist/` | 当前v0.4.160本机候选EXE、统一ZIP、UXP ZIP与两份校验，共5项；正式159清单与包已归档，公开Release仍159 |
| `.runtime/` | 当前构建／测试证据及仍在使用的本地数据，忽略提交 |
| `.local/design/` | 用户的完整 Figma ZIP／JSON 原稿，忽略提交 |
| `.local/archive/dist/` | 旧发行物与版本回退副本 |
| `.local/archive/runtime/` | 历史诊断、预览、配置备份、浏览器数据及恢复资料 |
| `.local/recovery/releases/` | 实际运行入口及配置的版本回退副本（保留144-before145及145-before146） |
| `.local/recovery/sample-documents/` | 原实验 PSD |
| `.local/recovery/git-history/private-history-backup.git` | 公开前的原始 Git 历史备份 |

## 2026-10-12历史整理记录

原 `.runtime/`／`dist/` 路径与归档目的地的对应关系在本机 `.local/archive/organization-manifest.json`。README、TODO 中旧版本的证据路径按此索引查找；当前 v0.4.115、公开及发布验收证据保留原位。旧热键诊断目录 `.runtime/capslock-history/` 的日志仍被占用，保留原位，没有中断进程。

删除对象仅为可重新构建的旧 PyInstaller 缓存、根目录构建缓存／字节码和空的 `Assest/`。原稿、PSD、旧发行包、用户配置、恢复文件及 Git 历史均保留。根目录 `Lib/`、`Scripts/`、`Include/`、`pyvenv.cfg` 属于当前 Python 环境，不作为杂项删除。

Figma 图标生成器默认读取 `.local/design/151500PX.figma-export.zip`，也可显式传入其他本地导出路径，兼容旧根目录路径。公开构建直接使用 `native/` 中已生成的几何／SVG，不需要完整原稿。

当次仅整理目录和工具路径，没有修改 UI、插件行为或发行二进制；已发布 v0.4.115 的 ZIP 不重新打包或覆盖。恢复旧运行版本前应正常退出当前服务、核对版本与配置，不直接覆盖运行中的 EXE。

后续v0.4.116功能更新后，v0.4.115公开附件归档在`.local/archive/dist/v0.4.115-published/`，旧运行EXE在`.local/recovery/releases/0.4.115/`。此移动发生在初轮目录整理索引之后，原附件内容保持不变。

整理后222项回归通过，13份图标生成输出及当前发行ZIP哈希不变。运行服务／菜单／热键仍为原进程，dist与实际组件一致，UXP仍为0.3.7。按文件长度统计净减少约597MiB，主要为可重新构建的缓存；约8.4GiB归档资料仍保留在本机，不计为释放空间。核验记录在`.runtime/organization-verification.json`。没有UI／执行行为修改，无需重新构建或重启宿主。

## 当前交付和维护工具

145公开ZIP不因后续文档同步重打包。旧144发行物归档`.local/archive/dist/v0.4.144-before145/`，运行入口及用户配置回退在`.local/recovery/releases/0.4.144-before145/`。GitHub发行页仅保留最新版，Git标签／源码历史和本地备份保留。

`tools/inspect-panels.ps1`采集窗口／面板／触发链；`tools/inspect-uxp.ps1`采集安装及宿主加载记录，二者用途不同。最新独立脚本从源码获取，不以旧公开包内容推断最新脚本版本。`.runtime/profile146-*`中的146是实验代号，实际受测程序仍为145，不代表发布了146。用户未跟踪的设计原稿目录继续原位保留，不纳入发行物。

146同时内置tools/inspect-panels.ps1与tools/inspect-uxp.ps1，默认从后台统一诊断调用；综合报告及分项原始采集写入实际数据目录diagnostics/，不含凭据配置。145运行入口回退位于.local/recovery/releases/0.4.145-before146/。

147用户索引维护的私有恢复副本位于数据目录uxp-management/backups/<标识>/PS-index-recovery.json；共享PS.json不纳入整文件所有权或覆盖式回退，安装快照只合并恢复本插件条目。146运行入口回退位于.local/recovery/releases/0.4.146-before147/。

148交付：147回退位于.local/recovery/releases/0.4.147-before148及.local/archive/dist/v0.4.147-before148。临时读取探针已从External和用户加载索引移除；.runtime仅保留测试来源与报告，不分发Adobe内部SDK摘录。

149回退保留于.local/recovery/releases/0.4.148-before149和.local/archive/dist/v0.4.148-before149；UXP19保持，PS无需重启。

150：149回退位于.local/recovery/releases/0.4.149-before150及.local/archive/dist/v0.4.149-before150；蒙版事务、重启加载和四主题导出证据位于.runtime/mask150*及shape-live-0.4.150.json，不公开用户配置／文档。

154：副屏维护入口tools/test-quiet-ps.py与quiet_ps_session.py；使用和限制见docs/QUIET-TESTING.md，完成恢复见docs/MENU-RECOVERY.md及Wiki。153回退保留于.local/recovery/releases/0.4.153-before154和.local/archive/dist/v0.4.153-before154。实体键鼠与视频掉帧仍单列，安全暂停不是完整测试通过。

155：新增frontend/src/shortcuts.mjs及对应测试，使用说明docs/SHORTCUTS.md／Wiki；原生组件与UXP23不变。154回退位于.local/recovery/releases/0.4.154-before155和.local/archive/dist/v0.4.154-before155；dist当前仅155发行物。

156：backend/mask_preview.py为单请求控制快照发布与会话生命周期；tools/verify-mask-preview.py为自建文档受限CPU／正常对照，文档docs/MASK-PREVIEW.md／Wiki。私有证据在.runtime/mask-preview-live-*，不公开本机凭据。正式运行入口与发行物仍分别核验，155回退预留于.local/recovery/releases/0.4.155-before156和.local/archive/dist/v0.4.155-before156。

157最终公开交付：dist仅157 EXE／ZIP／UXP ZIP／SHA256／更新清单六项。155发行物仍在.local/archive/dist/v0.4.155-before156，156未公开候选及包在.local/archive/dist/v0.4.156-before157；实际156入口／配置回退在.local/recovery/releases/0.4.156-before157，155稳定入口回退另存保留。所有Git标签保留。

158实机工具：tools/verify-paint-preview.py覆盖颜色预览、交叉编辑、普通填充／渐变；tools/verify-mask-preview.py覆盖蒙版回归。最终报告入口.runtime/live158-reports.json；旧157发行包归档.local/archive/dist/v0.4.157-before158，实际EXE与配置回退.local/recovery/releases/0.4.157-before158。

158公开交付：dist仅当前六项；旧157发行包、实际EXE与配置已按上述目录保留，所有Git标签与源码历史保持。

159回退：.local/archive/dist/v0.4.158-before159保留158完整发行包，.local/recovery/releases/0.4.158-before159保留实际入口与配置；文档恢复副本在.local/recovery/documents/panels159-1792227890664024000，原稿与所有源码标签保留。

159公开交付：dist仅当前六项；旧158发行包、实际EXE与配置已按上述目录保留，所有Git标签与源码历史保持。

160本机候选：实际入口和dist/PhotoshopMenu.exe为160／UXP27；dist现为160候选完整5项，与.runtime/release160-ready一致；正式159包／清单已归档保留，160尚无公开更新清单。旧159实际入口／配置及完整dist分别保存在.local/recovery/releases/0.4.159-before160与.local/archive/dist/v0.4.159-before160。画布目视确认前不发布或删除159 Release。
