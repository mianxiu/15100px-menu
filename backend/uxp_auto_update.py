"""Follow newer bundled UXP versions only while Photoshop is normally closed."""
import time
from .plugins import version
from .settings import atomic_json

class UxpAutoUpdate:
    def __init__(self, runtime):
        self.path=runtime/'uxp-auto-update.json'
        self.phase='idle';self.message='等待检查内置 UXP';self.failed_key=None;self.checked=0

    @property
    def enabled(self):
        import json
        try:return json.loads(self.path.read_text('utf-8')).get('enabled',True) is True
        except FileNotFoundError:return True
        except (OSError,ValueError):return False

    def snapshot(self):return {'enabled':self.enabled,'phase':self.phase,'message':self.message}

    def set_enabled(self, enabled):
        if type(enabled) is not bool:raise ValueError('自动更新选项必须为布尔值')
        atomic_json(self.path,{'enabled':enabled});self.failed_key=None;self.checked=0
        self.phase='idle' if enabled else 'disabled'
        self.message='已启用 UXP 跟随更新' if enabled else '已关闭 UXP 跟随更新'
        return self.snapshot()

    def step(self, manager, blocked=False):
        if not self.enabled:
            self.phase='disabled';return self.snapshot()
        s=manager.status()
        if not s['installed'] or not s['enabled']:
            self.phase='inactive';self.message='未安装或已禁用；保留当前选择';return self.snapshot()
        if s['error']:
            self.phase='blocked';self.message='安装异常，请在插件管理中检查';return self.snapshot()
        if s.get('minimum_declaration_pending') and version(s['version'])==version(s['bundled_version']):
            if blocked:
                self.phase='waiting';self.message='操作或结果待核对，稍后同步最低版本声明';return self.snapshot()
            key=('minimum',s['version'],s['bundled_version'])
            if self.failed_key==key:return self.snapshot()
            try:s=manager.sync_minimum_declaration()
            except Exception:
                self.failed_key=key;self.phase='error';self.message='最低版本声明未同步，请在插件管理中检查';return self.snapshot()
        registration=s.get('registration',{})
        if registration.get('state') in ('invalid','disabled'):
            self.phase='blocked';self.message='加载登记需要检查，请在插件管理中修复';return self.snapshot()
        repair=registration.get('auto_repair',False)
        if not repair and version(s['version'])>=version(s['bundled_version']):
            self.phase='current';self.message='已安装版本已跟随内置插件';return self.snapshot()
        if blocked:
            self.phase='waiting';self.message='操作或结果待核对，稍后更新 UXP';return self.snapshot()
        if manager.running():
            self.phase='waiting';self.message='UXP 待更新；保存并关闭 PS 后自动安装';return self.snapshot()
        key=(s['version'],s['bundled_version'],registration.get('state'))
        if self.failed_key==key:return self.snapshot()
        try:
            if repair and version(s['version'])>=version(s['bundled_version']):manager.repair_registration()
            else:manager.install()
            self.phase='updated';self.message='UXP 加载登记已自动修复，下次启动 PS 生效' if repair else '内置 UXP 已自动安装，下次启动 PS 生效'
        except Exception:
            self.failed_key=key;self.phase='error';self.message='自动安装失败，旧版已按安装流程保留；请检查插件管理后重新启用跟随更新'
        return self.snapshot()
