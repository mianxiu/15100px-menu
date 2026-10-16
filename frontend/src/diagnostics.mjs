// Local presentation clock; never polls PS or changes diagnostic state.
export const diagnosticScopes=[['all','综合检测（推荐）'],['menu','菜单与快捷键'],['uxp','UXP安装与加载'],['runtime','运行与图层读取']];
export const diagnosticComponents={menu:'菜单与快捷键',uxp:'UXP安装与加载',runtime:'运行与图层读取'};
const findings={uxp_loaded:'UXP已连接',uxp_files_missing:'未找到当前用户的UXP插件文件',uxp_current_host_logs_unavailable:'未取得当前PS启动后的加载日志，暂不能判断扫描路径',uxp_user_external_scan_not_observed:'当前启动日志未记录用户External目录扫描；这是排查线索，尚非故障根因',uxp_load_unconfirmed:'插件文件存在，但PS加载尚未确认'};
Object.assign(findings,{uxp_registration_missing:'用户加载索引缺少本插件，请保存并关闭PS后修复加载登记',uxp_registration_disabled:'本插件加载登记已禁用，可在插件管理中主动修复并启用',uxp_registration_invalid:'加载索引异常或路径冲突，已保留原文件，请在插件管理中检查',uxp_registration_outdated:'本插件加载登记待同步，请保存并关闭PS后修复'});
export function diagnosticFinding(code){return findings[code] || '检测结果待核对';}
export function diagnosticClock(value={},now=0){
  const remaining=Math.max(0,(value.remaining_ms || 0)-Math.max(0,now-(value.received_at ?? now)));
  const seconds=Math.ceil(remaining/1000);
  let label=value.message || '尚未采集诊断';
  if(value.phase==='collecting' && !seconds && value.stage==='prepare')label='正在开始采集，请保持PS前台';
  if(value.phase==='collecting' && !seconds && value.stage==='sampling')label='正在等待采集结束，请保持PS前台';
  return {label,seconds,showSeconds:value.phase==='collecting' && seconds>0};
}
