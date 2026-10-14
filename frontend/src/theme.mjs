// Match native/MenuHost.cpp::theme(). Reuse the status heartbeat; never query PS.
export const menuThemes = Object.freeze({
  light: ['#f0f0f0','#fcfcfc','#292929','#545454','#a8a8a8','#cccccc','#d9d9d9','#dceeff','#c3ddf8','#1473e6'],
  'light-gray': ['#b8b8b8','#d1d1d1','#0f0f0f','#383838','#808080','#949494','#999999','#a8c7e2','#92b7d8','#1473e6'],
  'dark-gray': ['#535353','#454545','#f0f0f0','#d6d6d6','#878787','#666666','#3e3e3e','#354f6c','#2c4460','#4da6ff'],
  dark: ['#323232','#292929','#e1e1e1','#adadad','#737373','#474747','#262626','#2e4054','#27384c','#4da6ff'],
});
const tokens = ['background','fill','text','muted','disabled','border','divider','hover','active','accent'];
export function applyMenuTheme(root, requested) {
  // Missing/invalid status keeps the last valid theme, including on disconnect.
  const name = Object.hasOwn(menuThemes, requested) ? requested :
    Object.hasOwn(menuThemes, root.dataset.theme) ? root.dataset.theme : 'dark';
  if (root.dataset.theme === name) return name;
  root.dataset.theme = name;
  menuThemes[name].forEach((value, index) => root.style.setProperty('--ui-'+tokens[index], value));
  const light = name === 'light' || name === 'light-gray';
  root.style.colorScheme = light ? 'light' : 'dark';
  root.style.setProperty('--ui-danger', light ? '#9d2929' : '#ffb5b5');
  root.style.setProperty('--ui-good', light ? '#215838' : '#a6ddbc');
  root.style.setProperty('--ui-warn', light ? '#634600' : '#eed397');
  return name;
}
