# 目录与本地归档

2026-10-16同步：当前实际程序与dist为v0.4.148／内置UXP0.3.19。源码、历史实验、当前发行物和本地资料分别存放；下面明确标为2026-10-12的整理数据属于历史时点。

| 路径 | 用途 |
| --- | --- |
| `tools/benchmark-layer-snapshots.py`、`tools/fixtures/selection-context-0.3.18.cjs` | 新鲜生产读取测量、冻结旧算法语义对照；不随运行入口加载 |
| `main.py`、`start.ps1`、`build-exe.ps1` | 当前启动／构建入口 |
| `backend/`、`frontend/`、`native/`、`uxp/`、`jsx/` | 当前实现与内置资源 |
| `photoshop_action/` 与根目录 COM 兼容模块 | 后端仍引用的兼容代码 |
| `tools/`、`tests/` | 维护工具与自动回归 |
| `legacy/` | 早期独立实验，不属于当前运行入口 |
| `dist/` | 当前v0.4.148 EXE、统一ZIP、UXP ZIP、校验文件及PhotoshopMenu-update.json；旧发行物另行归档保留 |
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
