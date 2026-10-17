const messages={
 result_unconfirmed:'操作结果待核对，已保留原请求保护',
 plugin_installation_invalid:'插件安装状态异常，请检查插件管理',
 plugin_not_ready:'PS已启动，插件连接尚未就绪',
 host_version_unrecognized:'无法识别PS版本，兼容性待核验',
 host_version_unsupported:'PS版本低于当前支持范围',
 plugin_version_unrecognized:'无法识别已加载插件版本',
 plugin_reload_required:'已加载与已安装插件版本不同，请保存并正常重启PS',
 redraw_api_missing:'当前PS未提供预期的实时重绘接口',
 redraw_capability_unreported:'插件未报告重绘能力，实时预览兼容性待核验',
 redraw_capability_lost:'相较上次正常自检，实时重绘能力发生变化',
 legacy_preview_pending:'当前使用兼容草稿，旧版实时预览尚待修复',
 task_failed:'最近操作失败，已保存状态与耗时线索',
 task_result_unknown:'最近操作结果未知，请核对原请求',
 status_unavailable:'后台状态读取异常，已保留线索',
 status_format_unknown:'状态格式发生变化，已保留兼容性线索'
};
export function healthFinding(code){return messages[code] || '未知兼容性线索，请导出报告';}
export function healthView(value={}){
 return {message:value.message || '等待版本与连接状态',
   alert:value.attention===true && value.acknowledged!==true,
   ready:value.ready===true,findings:Array.isArray(value.findings)?value.findings:[],
   versions:value.versions || {}};
}
