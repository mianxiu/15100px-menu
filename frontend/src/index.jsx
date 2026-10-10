import {render} from 'solid-js/web';
import {createSignal, onMount, onCleanup, For, Show} from 'solid-js';
import {Client} from './client.mjs';
import './style.css';

const pages = [['overview','运行状态'],['settings','菜单与快捷键'],['plugins','插件管理'],['logs','运行日志']];
const keyLabels = {toggle:'按住唤出 / 松开执行', hide:'收起菜单', select:'选择组内图层', color:'橙色图层标签', moveToTop:'移到顶部', moveToBottom:'移到底部'};
function App() {
  const [connection,setConnection] = createSignal('connecting');
  const [state,setState] = createSignal({photoshop:{},plugin:{active:{}},settings:{shortcuts:{}}});
  const [page,setPage] = createSignal('overview');
  const [form,setForm] = createSignal(null);
  const [dirty,setDirty] = createSignal(false);
  const [working,setWorking] = createSignal(false);
  const [notice,setNotice] = createSignal({message:'在 Photoshop 前台按住 CapsLock 呼出环绕菜单，向左 / 右 / 上 / 下滑动选择，松开执行；回到中心松开取消。',ok:true});
  const [preview,setPreview] = createSignal(null);
  const [logs,setLogs] = createSignal('');
  const [update,setUpdate] = createSignal(null);
  function accept(data) {
    setState(data);
    if (!dirty()) setForm(structuredClone(data.settings));
  }
  const client = new Client(`ws://${location.host}/websocket`, status => {
    setConnection(status);
    if(status==='connected') client.request('status').then(accept).catch(error=>setNotice({ok:false,message:error.message}));
  }, event => {
    if(event.type==='status') accept(event.data);
    if(event.type==='notice') setNotice(event);
  });
  async function call(action,args={}) {
    setWorking(true);
    try {const result=await client.request(action,args); if(action==='status')accept(result); setNotice({ok:true,message:result.message || '操作完成'}); return result;}
    catch(error){setNotice({ok:false,message:error.message}); throw error;}
    finally{setWorking(false);}
  }
  const disabled = ()=>working() || connection()!=='connected';
  const perform = (action,args={})=>call(action,args).catch(()=>{});
  function edit(key,value){setDirty(true);setForm({...form(),[key]:value});}
  function shortcut(key,value){setDirty(true);setForm({...form(),shortcuts:{...form().shortcuts,[key]:value}});}
  async function save(){try{const result=await call('settings.save',{settings:form()});setForm(result.settings);setDirty(false);}catch{}}
  async function readLogs(){try{setLogs((await call('logs.read')).text);}catch{}}
  async function upload(event){
    const file=event.currentTarget.files?.[0]; if(!file) return;
    setWorking(true);setPreview(null);
    try{const body=new FormData();body.append('file',file);const response=await fetch('/api/plugins/preview',{method:'POST',body});const result=await response.json();if(!result.ok)throw new Error(result.error);setPreview(result.data);setNotice({ok:true,message:result.data.message});}
    catch(error){setNotice({ok:false,message:error.message});}
    finally{setWorking(false);event.target.value='';}
  }
  async function install(){try{await call('plugin.install',{token:preview().token});setPreview(null);setUpdate(null);}catch{}}
  async function check(){try{setUpdate(await call('plugin.check'));}catch{}}
  async function download(){try{setPreview(await call('plugin.download'));}catch{}}
  function choose(name){setPage(name);if(name==='logs')readLogs();}
  onMount(()=>client.connect());onCleanup(()=>client.close());
  return <div class="shell">
    <aside><div class="brand"><img src="/icon.png" alt=""/><div><strong>Photoshop Menu</strong><small>后台管理</small></div></div>
      <nav><For each={pages}>{([name,label])=><button classList={{selected:page()===name}} onClick={()=>choose(name)}>{label}</button>}</For></nav>
      <div class="aside-note">Dear ImGui 原生操作菜单<br/>仅在 Photoshop 内唤出</div><div class="version">{state().version ? `应用 v${state().version}${connection()==='connected'?'':'（上次连接）'}` : '应用版本待确认'}</div>
    </aside>
    <main><header><div><h1>{pages.find(([name])=>name===page())?.[1]}</h1><p>管理服务、菜单设置和 Photoshop 图层脚本</p></div><span classList={{badge:true,online:connection()==='connected'}}>{connection()==='connected'?'后台在线':connection()==='connecting'?'正在连接':'已断开 · 自动重连'}</span></header>
      <div classList={{notice:true,error:!notice().ok}} role="status">{notice().message}</div>
      <Show when={page()==='overview'}><div class="cards"><section><h2>Photoshop 连接</h2><strong class="status-value">{state().photoshop.message || '检查中…'}</strong><p>{state().photoshop.document || '当前没有可用文档'}</p><p>{state().photoshop.busy?'正在执行图层操作':'执行线程空闲'}</p></section><section><h2>原生操作菜单</h2><strong class="status-value">{state().settings.enabled?'已启用':'已暂停'}</strong><p>{state().desktop}</p><p>当前面板：{state().menu?.panel_context?.label || '通用操作'}（优先按鼠标悬停区域识别）</p><p>{state().menu?.ready?'C++ Dear ImGui 菜单已就绪（默认隐藏）':'原生菜单正在初始化或未启用桌面功能'}</p><p>打开 Photoshop 主窗口，把鼠标移入窗口，按 {state().settings.shortcuts?.toggle || 'CapsLock'}。</p></section></div>
        <section><h2>操作菜单与后台各自独立</h2><p>后台管理可以随时打开。图层选择、标色和排序在 Dear ImGui 菜单内完成，保留鼠标附近的唤出方式。</p><p>菜单打开后可取得焦点；切换到其他应用、关闭或最小化 Photoshop 会自动收起。后台页面不执行图层动作。</p><Show when={state().tray_error}><p class="error">托盘：{state().tray_error}</p></Show><div class="buttons"><button disabled={disabled()} onClick={()=>perform('status').then(()=>{})}>刷新连接状态</button><button class="danger" disabled={disabled() || state().photoshop.busy} onClick={()=>perform('service.quit')}>退出后台服务</button></div></section>
        <section><h2>当前运行版本</h2><p>{state().version ? `v${state().version}` : '待确认'}{connection()==='connected'?' · 服务在线':' · 等待重新连接确认'}</p><p>程序：{state().service?.executable || '此服务未提供程序路径'}</p><p>升级应用：先退出后台服务，等待退出完成，再替换并打开 PhotoshopMenu.exe。设置与脚本包会保留。</p></section>
      </Show>
      <Show when={page()==='settings' && form()}><section><h2>菜单行为</h2><div class="checks"><label><input type="checkbox" checked={form().enabled} onChange={e=>edit('enabled',e.target.checked)}/>启用 Photoshop 操作菜单与快捷键</label><label><input type="checkbox" checked={form().right_click_hide} onChange={e=>edit('right_click_hide',e.target.checked)}/>在菜单内右键收起</label><label><input type="checkbox" checked={form().open_control_on_start} onChange={e=>edit('open_control_on_start',e.target.checked)}/>启动时打开后台管理窗口</label></div><div class="fields"><label>菜单宽度<input type="number" min="300" max="1200" value={form().menu_width} onInput={e=>edit('menu_width',Number(e.target.value))}/></label><label>菜单高度<input type="number" min="240" max="1000" value={form().menu_height} onInput={e=>edit('menu_height',Number(e.target.value))}/></label></div><p>尺寸按屏幕 DPI 缩放，显示位置限制在 Photoshop 窗口与屏幕工作区内。</p></section>
        <section><h2>菜单快捷键</h2><div class="fields"><For each={Object.entries(keyLabels).filter(([key])=>['toggle','hide'].includes(key))}>{([key,label])=><label>{label}<input value={form().shortcuts[key]} onInput={e=>shortcut(key,e.target.value)}/></label>}</For></div><p>支持 CapsLock、Tab、Esc、Space、F1–F12，或 ctrl / alt / shift / capslock / tab 组合键。图层操作的快捷键在插件管理中配置。</p><p>Photoshop 内右键始终保留原生行为；按住 CapsLock 唤出自定义菜单，在自定义菜单内部右键可打开更多操作。勾选“在菜单内右键收起”后改为右键关闭。点击外部或成功执行一个动作也会关闭菜单。</p></section>
        <section><h2>脚本更新源</h2><label>更新清单 HTTPS 地址<input type="url" placeholder="https://…/updates.json" value={form().update_url} onInput={e=>edit('update_url',e.target.value)}/></label><p>留空时仍可通过 ZIP 安装脚本包。保存后在插件管理中检查更新。</p><div class="buttons"><button class="primary" disabled={disabled() || !dirty()} onClick={save}>保存并立即生效</button><button disabled={!dirty()} onClick={()=>{setForm(structuredClone(state().settings));setDirty(false);}}>放弃修改</button></div></section>
      </Show>
      <Show when={page()==='plugins'}><section><h2>Photoshop 图层脚本包</h2><div class="package"><img src="/icon.png" alt=""/><div><strong>{state().plugin.active.name || 'Photoshop Menu 图层操作'}</strong><p>当前版本 {state().plugin.active.version} · {state().plugin.installed?'已安装升级包':'随应用提供的内置版本'}</p></div></div><p>管理 COM 调用的 JSX 脚本包。更换脚本后即时生效，Dear ImGui 菜单保持不变。</p><div class="buttons"><label class="upload">选择 ZIP 升级包<input type="file" accept=".zip" disabled={disabled()} onChange={upload}/></label><a class="button" href="/api/plugins/export">导出当前脚本包</a><button disabled={disabled() || !state().plugin.can_rollback || state().photoshop.busy} onClick={()=>perform('plugin.rollback')}>回滚上一版本</button><button disabled={disabled() || !state().plugin.installed || state().photoshop.busy} onClick={()=>perform('plugin.uninstall')}>卸载升级包，恢复内置版</button></div></section>
        <Show when={form()}><section><h2>子脚本快捷键</h2><div class="fields"><For each={Object.entries(keyLabels).filter(([key])=>!['toggle','hide'].includes(key))}>{([key,label])=><label>{label}<input value={form().shortcuts[key]} onInput={e=>shortcut(key,e.target.value)}/></label>}</For></div><p>这些快捷键属于图层子脚本。CapsLock 为按住按键；仅 Photoshop 或其弹出菜单获得焦点时生效。</p><div class="buttons"><button class="primary" disabled={disabled() || !dirty()} onClick={save}>保存并立即生效</button><button disabled={!dirty()} onClick={()=>{setForm(structuredClone(state().settings));setDirty(false);}}>放弃修改</button></div></section></Show>
        <Show when={preview()}><section class="preview"><h2>待安装脚本包</h2><strong>{preview().manifest.name || preview().manifest.id} · v{preview().manifest.version}</strong><p>文件清单、版本和 SHA256 已校验。安装期间不会执行 Photoshop 脚本。</p><div class="buttons"><button class="primary" disabled={disabled() || state().photoshop.busy} onClick={install}>安装并启用</button><button onClick={()=>setPreview(null)}>关闭预览</button></div></section></Show>
        <section><h2>在线更新</h2><p>{state().settings.update_url || '尚未配置更新清单地址。可在菜单与快捷键设置中填写。'}</p><div class="buttons"><button disabled={disabled() || !state().settings.update_url} onClick={check}>检查更新</button><Show when={update()}><span>{update().available?`发现 v${update().version}`:'当前已是更新源中的最新版本'}</span><button disabled={disabled() || !update()?.available} onClick={download}>下载并预览</button></Show></div></section>
      </Show>
      <Show when={page()==='logs'}><section><div class="section-heading"><h2>最近 200 行服务日志</h2><button disabled={disabled()} onClick={readLogs}>刷新日志</button></div><pre>{logs() || '暂无日志'}</pre><p>应用数据目录：{state().data_dir || '.runtime'}。原生菜单的启动诊断另存于该目录的 overlay.log。</p></section></Show>
    </main>
  </div>;
}
render(()=><App/>,document.getElementById('root'));
