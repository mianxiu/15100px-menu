export function replacePreview(text,find,replacement) {
  const normalize=value=>value.replace(/\r\n|\n/g,'\r');
  find=normalize(find);replacement=normalize(replacement);
  if(!find)return {text,count:0};
  const parts=text.split(find);
  return {text:parts.join(replacement),count:parts.length-1};
}

export function defaultGroups(text) {
  const lines=text.split('\r').length,size=Math.ceil(lines/64),groups=[];
  for(let from=1;from<=lines;from+=size){const to=Math.min(lines,from+size-1);groups.push(from===to?String(from):`${from}-${to}`);}
  return groups.join(',');
}

export function splitPreview(text,expression) {
  const fail=()=>({breaks:[],groups:[],error:'分组须按顺序覆盖所有行，例如1-3,4,5-7，最多64组'});
  if(typeof expression!=='string'||expression.length>1000)return fail();
  const lines=text.split('\r'),ends=[];let offset=0;
  for(let index=0;index<lines.length;index++){offset+=lines[index].length+(index<lines.length-1?1:0);ends.push(offset);}
  const tokens=expression.replace(/，/g,',').split(',');
  if(tokens.length>64)return fail();
  let next=1;const breaks=[];
  for(const token of tokens){
    const match=/^\s*([1-9]\d*)(?:\s*-\s*([1-9]\d*))?\s*$/.exec(token);
    if(!match)return fail();
    const from=Number(match[1]),to=Number(match[2]||match[1]);
    if(from!==next||to<from||to>lines.length)return fail();
    const end=ends[to-1];if(end>0&&end!==breaks.at(-1))breaks.push(end);next=to+1;
  }
  if(next!==lines.length+1)return fail();
  const groups=[];let from=0;
  for(const end of breaks){const to=text[end-1]==='\r'?end-1:end,value=text.slice(from,to);if(/\S/.test(value))groups.push(value);from=end;}
  return {breaks,groups,error:groups.length<2?'拆分需要至少两组非空文字':''};
}
