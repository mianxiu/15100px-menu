import english from './locales/en.mjs';

// Source Chinese is the default locale. No DOM mutation or text guessing.
export function translate(value,language='zh-CN') {
  if(value==null)return '';
  const text=String(value);
  if(language!=='en')return text;
  if(Object.hasOwn(english,text))return english[text];
  const trimmed=text.trim();
  if(Object.hasOwn(english,trimmed))return text.replace(trimmed,english[trimmed]);
  for(const [source,target]of Object.entries(patterns)){
    const match=text.match(source);
    if(match)return target.replace(/\$(\d+)/g,(_,n)=>translate(match[Number(n)] || '',language));
  }
  // Native error details, executable paths and service logs stay verbatim.
  return text;
}

const patterns={
  '^(.+)已完成$':'$1 completed',
  '^插件文件被外部修改：(.+)$':'Plugin files changed externally: $1',
  '^插件目录含非管理文件，已保留：(.+)$':'Unmanaged files found in plugin directory; retained: $1',
  '^插件文件为空：(.+)$':'Empty plugin file: $1',
  '^UXP 插件最低 Photoshop 版本必须为 (.+)$':'Minimum Photoshop version must be $1',
  '^已清除 (\\d+) 个图层的标签，并核验为无颜色；父组仍有颜色标签，图层面板可能继续显示父组颜色$':'Cleared labels on $1 layers; verified no color. The parent group has a label which may still appear in the Layers panel',
  '^已清除 (\\d+) 个图层的标签，并核验为无颜色$':'Cleared labels on $1 layers; verified no color',
  '^已将 (\\d+) 个图层标记为 (.+)$':'Labeled $1 layers: $2',
  '^应用 v(.+)$':'App v$1',
  '^发现 v(.+)$':'Version v$1 available',
  '^插件名称：(.+)$':'Plugin name: $1',
  '^检测目录：(.+)$':'Detected directory: $1',
  '^Photoshop 启动失败：(.+)$':'Photoshop startup failed: $1',
  '^UXP 插件已安装并启用；正常启动 Photoshop 后自动加载；(.+)$':'UXP installed and enabled; $1',
  '^已在 (.+) 个图层上设置 (.+) 标签并核验$':'Set $2 labels on $1 layers and verified',
};

export const supportedLanguages=['zh-CN','en'];
