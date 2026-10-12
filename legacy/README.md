# 历史实验脚本

这里集中保留项目早期的 COM、热键、缩放和 ExtendScript 实验，供理解历史实现使用。这些脚本不属于当前启动、构建或自动测试入口，不保证可直接运行；部分会直接修改 Photoshop 文档，不要批量执行或导入。

当前应用入口是根目录 `main.py`，后端在 `backend/`，原生菜单在 `native/`，UXP 执行端在 `uxp/`，维护工具和回归测试分别在 `tools/`、`tests/`。根目录的 `app.py`、`photoshopcomserver.py`、`photoshopcomclient.py` 为兼容接口；`photoshop_action/` 仍被后端引用，必须保留。

原实验 PSD 不随公开仓库分发；本机已归档到 `.local/recovery/sample-documents/`。
