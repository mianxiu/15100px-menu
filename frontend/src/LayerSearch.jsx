import {createSignal,For,Show} from 'solid-js';

const kinds=[['all','全部类型'],['pixel','像素图层'],['text','文字图层'],['group','图层组'],['shape','形状图层'],['smart-object','智能对象'],['adjustment','调整图层'],['fill','填充图层'],['other','其他图层']];

export default function LayerSearch(props) {
  const [name,setName]=createSignal(''),[documentName,setDocumentName]=createSignal(''),[kind,setKind]=createSignal('all');
  const [result,setResult]=createSignal(null),[pending,setPending]=createSignal(false),[error,setError]=createSignal('');
  const t=value=>props.t(value),disabled=()=>pending()||props.disabled();
  async function search(event) {
    event.preventDefault();setPending(true);setResult(null);setError('');
    try {setResult(await props.call('layers.search',{name:name(),document:documentName(),type:kind()}));}
    catch(error){setError(error.message);}finally{setPending(false);}
  }
  async function focus(index) {
    setPending(true);setError('');
    try {await props.call('layers.focus',{search_id:result().search_id,index});}
    catch(error){setError(error.message);}finally{setPending(false);}
  }
  return <section>
    <p>{t('搜索已打开文档；点击定位会切到Photoshop并单选该图层，不改变图层可见性。')}</p>
    <form onSubmit={search} class="layer-search-form">
      <label>{t('文件名包含')}<input value={documentName()} onInput={event=>setDocumentName(event.currentTarget.value)} maxlength="200" disabled={disabled()}/></label>
      <label>{t('图层名包含')}<input value={name()} onInput={event=>setName(event.currentTarget.value)} maxlength="200" disabled={disabled()}/></label>
      <label>{t('图层类型')}<select aria-label={t('图层类型')} value={kind()} onChange={event=>setKind(event.currentTarget.value)} disabled={disabled()}><For each={kinds}>{([value,label])=><option value={value}>{t(label)}</option>}</For></select></label>
      <button type="submit" disabled={disabled()}>{t(pending()?'正在处理…':'搜索图层')}</button>
    </form>
    <Show when={error()}><p class="error" role="alert">{t(error())}</p></Show>
    <Show when={result()}><p role="status">{t('找到图层：')}{result().items.length} · {t('已扫描：')}{result().scanned}<Show when={result().truncated}> · {t('达到搜索上限，请缩小条件')}</Show></p>
      <div class="layer-search-results"><table><thead><tr><th>{t('文件名')}</th><th>{t('图层名')}</th><th>{t('图层类型')}</th><th>{t('操作')}</th></tr></thead><tbody><For each={result().items}>{(row,index)=><tr><td>{row.document_name}</td><td>{row.name}<small> ID {row.layer_id}</small></td><td>{t(kinds.find(([value])=>value===row.type)?.[1]||'其他图层')}</td><td><button disabled={disabled()} onClick={()=>focus(index())}>{t('定位')}</button></td></tr>}</For></tbody></table></div>
      <Show when={!result().items.length}><p>{t('没有匹配的图层')}</p></Show>
    </Show>
  </section>;
}
