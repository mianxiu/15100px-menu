# GitHub 应用更新

从 v0.4.120 起，后台“运行状态 → 应用更新”检查本仓库 GitHub Releases。

更早版本尚无应用更新入口，首次升级到120需正常退出后手动替换一次；从120起以后可在后台更新。本机已由本轮实施切换120。

1. 默认每24小时自动检查正式版本，可关闭；不会自动下载或安装。手动检查不受每日间隔限制。
2. 新版可用时点击“下载并校验”，下载在线程中完成、显示进度；断网或校验失败不改变现有程序，可重新下载。
3. 完成并核对所有任务，收起菜单、保存后台设置，再点击“安装并重启后台”。助手等待旧服务及打包父进程正常退出，备份旧EXE、原子替换原运行入口，按原端口／数据目录／启动模式重开。浏览器自动重连，不重复安装。
4. Photoshop和文档保持打开。内置UXP随应用更新，但不强行替换已加载的插件；如有新版，保存并关闭PS后在“插件管理”安装内置版并重新加载。应用和插件版本分别显示。

只有检查和下载需要网络；菜单、任务核对和插件执行仍离线。无需GitHub账号、token、git或Adobe下载工具。使用系统代理，不附带本机代理地址，不改变PS防火墙规则。断网仍可使用统一ZIP：正常退出后台后替换EXE，按需更新内置插件。

## 校验与恢复

- 固定源为`mianxiu/15100px-menu`的`/releases/latest`，只接受已发布、非预览版本且版本号高于当前；不自动降级。
- 附件必须为`PhotoshopMenu-Backend-<版本>.zip`及同名`.sha256`，HTTPS地址绑定仓库／标签／文件名，仅允许GitHub发行附件CDN重定向。
- 核对GitHub SHA256 digest（如有）、ZIP SHA256、包内EXE SHA256、Windows产品身份和版本。拒绝不安全路径、重复条目、过大文件、独立UXP包及源码ZIP；仅提取EXE，不执行ZIP中其他脚本。SHA256校验不等同代码签名。
- 暂存、任务和旧程序在数据目录`application-updates/`；检查偏好／发行缓存在`application-update.json`。下载及安装尝试使用独立目录，旧就绪标记不能触发新安装。不改菜单设置、UXP凭据和文档。
- 忙碌、排队、PS启动中、未知结果待核对、菜单未收起时拒绝安装，准备期间拒绝新修改。不取消或重发PS命令，不转COM。
- 只等待原进程，不强制结束。旧进程未退出就取消替换；新进程明确退出且启动失败时恢复旧EXE和安装归属记录。新版仍运行但未确认就绪时保留备份并报告原因，不强行覆盖运行程序。

## 维护约定

发布统一ZIP和SHA256，保留已发布附件，不覆盖内容。后续EXE须保持`--apply-update <job.json>`的schema 1兼容，供已安装版使用。不要把预览版、草稿、源码或独立UXP ZIP当作应用更新附件。

参考[GitHub Releases API](https://docs.github.com/en/rest/releases/releases)、[附件API](https://docs.github.com/en/rest/releases/assets)和[REST最佳实践](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)。使用ETag条件请求；匿名请求仍可能限流，显示错误，不高频重试。
