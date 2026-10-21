import {createSignal,createMemo,Show} from 'solid-js';
import {replacePreview,splitPreview,defaultGroups} from './text-tools.mjs';

export default function TextTools(props) {
  const [snapshot,setSnapshot]=createSignal(null),[find,setFind]=createSignal(''),[replacement,setReplacement]=createSignal('');
  const [pending,setPending]=createSignal(false),[error,setError]=createSignal('');
  const [grouping,setGrouping]=createSignal('');
  const t=value=>props.t(value),disabled=()=>pending()||props.disabled();
  const preview=createMemo(()=>replacePreview(snapshot()?.text||'',find(),replacement()));
  const split=createMemo(()=>splitPreview(snapshot()?.text||'',grouping()));
  async function read() {
    setPending(true);setError('');setSnapshot(null);
    try {const value=await props.call('text.read',{});setSnapshot(value);setGrouping(defaultGroups(value.text));}catch(error){setError(error.message);}finally{setPending(false);}
  }
  async function apply() {
    setPending(true);setError('');
    try {await props.call('text.replace',{revision:snapshot().revision,find:find(),replacement:replacement()});setSnapshot(null);}
    catch(error){setError(error.message);}finally{setPending(false);}
  }
  async function applySplit() {
    setPending(true);setError('');
    try {await props.call('text.split',{revision:snapshot().revision,breaks:split().breaks});setSnapshot(null);}
    catch(error){setError(error.message);}finally{setPending(false);}
  }
  return <section>
    <Show when={props.mode==='split'} fallback={<p>{t('在PS中单选文字图层，再读取。普通查找区分大小写；预览和取消不写PS，确认替换只需一次撤销。')}</p>}>
      <p>{t('读取文字后按原换行拆分，也可合并连续行号。确认将用独立可编辑文字层替换原层，一次撤销恢复；预览和取消不写PS。')}</p>
    </Show>
    <div class="buttons"><button disabled={disabled()} onClick={read}>{t('读取选中文字')}</button></div>
    <Show when={error()}><p class="error" role="alert">{t(error())}</p></Show>
    <Show when={snapshot()}>
      <p>{snapshot().name}</p>
      <Show when={props.mode!=='split'}>
      <div class="fields"><label>{t('查找文字')}<textarea maxlength="200" value={find()} disabled={disabled()} onInput={event=>setFind(event.currentTarget.value)}/></label>
        <label>{t('替换为')}<textarea maxlength="500" value={replacement()} disabled={disabled()} onInput={event=>setReplacement(event.currentTarget.value)}/></label></div>
      <label>{t('原文字')}<textarea readonly rows="5" value={snapshot().text.replace(/\r/g,'\n')}/></label>
      <label>{t('替换预览')}<textarea readonly rows="5" value={preview().text.replace(/\r/g,'\n')}/></label>
      <p role="status">{t('匹配数量：')}{preview().count} · {t('新文字长度：')}{preview().text.length}</p>
      <div class="buttons"><button disabled={disabled()||!preview().count||!preview().text.length||preview().text.length>20000||preview().text===snapshot().text} onClick={apply}>{t('确认替换')}</button>
        <button disabled={disabled()} onClick={()=>{setSnapshot(null);setError('');}}>{t('取消预览')}</button></div>
      <p>{t('插入文字沿用匹配起点样式；未替换文字保留原样式。最多20000字符，缺失字体或手动字距先在PS中处理。')}</p>
      </Show>
      <Show when={props.mode==='split'}>
        <label>{t('原文字（含行号）')}<textarea readonly rows="7" value={snapshot().text.split('\r').map((line,index)=>`${index+1}: ${line}`).join('\n')}/></label>
        <label>{t('按行分组')}<input maxlength="1000" value={grouping()} disabled={disabled()} onInput={event=>setGrouping(event.currentTarget.value)}/></label>
        <p>{t('例如1-3,4,5-7：前三行一组，第4行一组，第5到7行一组；按顺序覆盖所有行，最多64组。')}</p>
        <Show when={split().error}><p class="error" role="status">{t(split().error)}</p></Show>
        <label>{t('拆分预览')}<textarea readonly rows="7" value={split().groups.map((text,index)=>`${index+1}:\n${text.replace(/\r/g,'\n')}`).join('\n\n')}/></label>
        <p>{t('独立文字层数量：')}{split().groups.length}</p>
        <div class="buttons"><button disabled={disabled()||!!split().error||split().breaks.length<2} onClick={applySplit}>{t('确认拆分并替换原层')}</button>
          <button disabled={disabled()} onClick={()=>setGrouping(defaultGroups(snapshot().text))}>{t('重置分组')}</button>
          <button disabled={disabled()} onClick={()=>{setSnapshot(null);setError('');}}>{t('取消预览')}</button></div>
        <p>{t('空白行保留原间距，不生成空图层。位置、字形或样式无法核验时整项恢复；路径、扭曲、剪贴及图层效果暂不拆分。')}</p>
      </Show>
    </Show>
  </section>;
}
