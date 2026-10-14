import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {menuThemes, applyMenuTheme} from '../src/theme.mjs';

function root() {
  const properties = new Map();
  return {dataset:{}, style:{setProperty:(key,value)=>properties.set(key,value)}, properties};
}
function luminance(hex) {
  return [1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255)
    .map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4)
    .reduce((sum,n,i)=>sum+n*[.2126,.7152,.0722][i],0);
}
test('four PS themes preserve native neutral palette and readable normal/hover/selected text',()=>{
  const native = readFileSync(new URL('../../native/MenuHost.cpp',import.meta.url),'utf8');
  const names = ['background','fill','text','muted','disabled','border','divider'];
  for (const [index,name] of names.entries()) {
    const values = native.match(new RegExp(name+'\\[\\]=\\{([0-9,]+)\\}'))[1].split(',');
    Object.values(menuThemes).forEach((palette,i)=>{
      assert.equal(palette[index], '#'+Number(values[i]).toString(16).padStart(2,'0').repeat(3),name);
    });
  }
  for (const [name,palette] of Object.entries(menuThemes)) {
    for (const fg of [palette[2],palette[3]]) for (const bg of [palette[0],palette[1],palette[7],palette[8]]) {
      const a=luminance(fg),b=luminance(bg);
      assert.ok((Math.max(a,b)+.05)/(Math.min(a,b)+.05)>=4.5,`${name}: ${fg} on ${bg}`);
    }
  }
});
test('status updates change theme locally and missing/reconnected state preserves it',()=>{
  const html=root();
  assert.equal(applyMenuTheme(html,undefined),'dark');
  assert.equal(html.style.colorScheme,'dark');
  assert.equal(applyMenuTheme(html,'light-gray'),'light-gray');
  assert.equal(html.style.colorScheme,'light');
  assert.equal(html.properties.get('--ui-fill'),'#d1d1d1');
  for(const value of [null,'unknown','constructor','__proto__',undefined]) {
    assert.equal(applyMenuTheme(html,value),'light-gray');
  }
  // Repeated heartbeats do not restyle controls or disturb form input.
  html.style.setProperty=()=>{throw new Error('redundant style update');};
  applyMenuTheme(html,'light-gray');
});
