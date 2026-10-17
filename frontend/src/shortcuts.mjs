// Shared option lists are built once; editing settings never queries Photoshop.
const modifiers=['ctrl','alt','shift','capslock','tab'];
const labels={ctrl:'Ctrl',alt:'Alt',shift:'Shift',capslock:'CapsLock',tab:'Tab',esc:'Esc',space:'Space'};
export const triggerKeys=['capslock','tab','esc','space',
  ...Array.from({length:12},(_,i)=>`f${i+1}`),
  ...Array.from({length:26},(_,i)=>String.fromCharCode(97+i)),
  ...Array.from({length:10},(_,i)=>String(i))];
export const keyLabel=key=>labels[key] || key.toUpperCase();
export const prefixOptions=Array.from({length:32},(_,mask)=>{
  const names=modifiers.filter((_,i)=>mask & (1<<i));
  return {value:names.join('+'),label:names.length?names.map(keyLabel).join(' + '):'无组合键',count:names.length};
}).sort((a,b)=>a.count-b.count);

export function shortcutParts(value=''){
  const names=value.trim().toLowerCase().split('+');
  const key=names.pop();
  return {prefix:modifiers.filter(name=>names.includes(name)).join('+'),key};
}

export function triggerAllowed(prefix,key){
  if(!triggerKeys.includes(key))return false;
  if(prefix){
    return key!=='capslock' && !prefix.split('+').includes(key);
  }
  // Match the existing backend grammar, including its accepted single F key.
  return ['capslock','tab','esc','space'].includes(key) || key.startsWith('f');
}

export function changePrefix(value,prefix){
  const {key}=shortcutParts(value);
  return triggerAllowed(prefix,key)?[prefix,key].filter(Boolean).join('+'):(prefix?prefix+'+':'');
}

export function changeTrigger(value,key){
  if(!key)return '';
  const {prefix}=shortcutParts(value);
  return [prefix,key].filter(Boolean).join('+');
}

export function shortcutError(value,required=false){
  if(typeof value!=='string')return '请选择按键';
  if(!value.trim())return required?'唤出与收起快捷键不能为空':'';
  const names=value.trim().toLowerCase().split('+'),key=names.at(-1),prefix=names.slice(0,-1);
  if(!key)return '请选择按键';
  if(prefix.some(name=>!modifiers.includes(name)) || !triggerKeys.includes(key))return '快捷键包含不支持的按键';
  if(new Set(names).size!==names.length)return '组合键与触发键不能重复';
  if(!triggerAllowed(prefix.join('+'),key))return '请为字母或数字选择组合键';
  return '';
}

export function shortcutErrors(values={}){
  const errors={},seen=new Map();
  for(const [name,value] of Object.entries(values)){
    if(['moveUp','moveDown'].includes(name))continue;
    const error=shortcutError(value,['toggle','hide'].includes(name));
    if(error){errors[name]=error;continue;}
    if(!value.trim())continue;
    const names=value.trim().toLowerCase().split('+'),key=names.pop();
    const identity=[...names.sort(),key].join('+');
    if(seen.has(identity))errors[name]=errors[seen.get(identity)]='快捷键不能重复';
    else seen.set(identity,name);
  }
  return errors;
}
