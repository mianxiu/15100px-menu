# 目录与本地归档

2026-10-12 整理完成后，源码、历史实验、当前发行物和本地资料分别存放。

| 路径 | 用途 |
| --- | --- |
| `main.py`、`start.ps1`、`build-exe.ps1` | 当前启动／构建入口 |
| `backend/`、`frontend/`、`native/`、`uxp/`、`jsx/` | 当前实现与内置资源 |
| `photoshop_action/` 与根目录 COM 兼容模块 | 后端仍引用的兼容代码 |
| `tools/`、`tests/` | 维护工具与自动回归 |
| `legacy/` | 早期独立实验，不属于当前运行入口 |
| `dist/` | 当前 v0.4.115 EXE、统一 ZIP、UXP ZIP、整理后的补充源码 ZIP 与校验文件 |
| `.runtime/` | 当前构建／测试证据及仍在使用的本地数据，忽略提交 |
| `.local/design/` | 用户的完整 Figma ZIP／JSON 原稿，忽略提交 |
| `.local/archive/dist/` | 旧发行物与版本回退副本 |
| `.local/archive/runtime/` | 历史诊断、预览、配置备份、浏览器数据及恢复资料 |
| `.local/recovery/sample-documents/` | 原实验 PSD |
| `.local/recovery/git-history/private-history-backup.git` | 公开前的原始 Git 历史备份 |

原 `.runtime/`／`dist/` 路径与归档目的地的对应关系在本机 `.local/archive/organization-manifest.json`。README、TODO 中旧版本的证据路径按此索引查找；当前 v0.4.115、公开及发布验收证据保留原位。旧热键诊断目录 `.runtime/capslock-history/` 的日志仍被占用，保留原位，没有中断进程。

删除对象仅为可重新构建的旧 PyInstaller 缓存、根目录构建缓存／字节码和空的 `Assest/`。原稿、PSD、旧发行包、用户配置、恢复文件及 Git 历史均保留。根目录 `Lib/`、`Scripts/`、`Include/`、`pyvenv.cfg` 属于当前 Python 环境，不作为杂项删除。

Figma 图标生成器默认读取 `.local/design/151500PX.figma-export.zip`，也可显式传入其他本地导出路径，兼容旧根目录路径。公开构建直接使用 `native/` 中已生成的几何／SVG，不需要完整原稿。

本次仅整理目录和工具路径，没有修改 UI、插件行为或发行二进制；已发布 v0.4.115 的 ZIP 不重新打包或覆盖。恢复旧运行版本前应正常退出当前服务、核对版本与配置，不直接覆盖运行中的 EXE。

整理后222项回归通过，13份图标生成输出及当前发行ZIP哈希不变。运行服务／菜单／热键仍为原进程，dist与实际组件一致，UXP仍为0.3.7。按文件长度统计净减少约597MiB，主要为可重新构建的缓存；约8.4GiB归档资料仍保留在本机，不计为释放空间。核验记录在`.runtime/organization-verification.json`。没有UI／执行行为修改，无需重新构建或重启宿主。
