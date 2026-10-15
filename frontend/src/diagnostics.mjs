// Local presentation clock; never polls PS or changes diagnostic state.
export function diagnosticClock(value={},now=0){
  const remaining=Math.max(0,(value.remaining_ms || 0)-Math.max(0,now-(value.received_at ?? now)));
  const seconds=Math.ceil(remaining/1000);
  let label=value.message || '尚未采集诊断';
  if(value.phase==='collecting' && !seconds && value.stage==='prepare')label='正在开始采集，请保持PS前台';
  if(value.phase==='collecting' && !seconds && value.stage==='sampling')label='正在等待采集结束，请保持PS前台';
  return {label,seconds,showSeconds:value.phase==='collecting' && seconds>0};
}
