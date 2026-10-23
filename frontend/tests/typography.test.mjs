import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,readdirSync} from 'node:fs';

const css=readFileSync(new URL('../src/admin.css',import.meta.url),'utf8');
const root=css.match(/:root\s*\{([^}]+)\}/)[1];
const tokens=Object.fromEntries([...root.matchAll(/(--ui-[\w-]+):([^;]+);/g)].map(m=>[m[1],m[2]]));
const value=key=>tokens[key].startsWith('var(')?value(tokens[key].slice(4,-1)):parseFloat(tokens[key]);

test('text hierarchy and line heights are shared, controls inherit body and small text stays readable',()=>{
  assert.equal(value('--ui-body-size'),value('--ui-control-size'));
  assert.equal(value('--ui-body-line'),value('--ui-control-line'));
  const roles=['secondary','body','section','emphasis','title'];
  assert.deepEqual(roles.map(role=>value('--ui-'+role+'-size')),[12,13,14,16,18]);
  for(const role of roles)assert.ok(value('--ui-'+role+'-line')>=value('--ui-'+role+'-size')*1.3,role);
  assert.match(css,/small\{font-size:var\(--ui-secondary-size\);line-height:var\(--ui-secondary-line\)/);
});

test('new styles and inline views cannot introduce literal text sizes, weights or shorthand fonts',()=>{
  for(const file of readdirSync(new URL('../src',import.meta.url),{recursive:true})) {
    if(!/\.(css|jsx|js|mjs)$/.test(file))continue;
    const source=readFileSync(new URL('../src/'+file,import.meta.url),'utf8');
    assert.doesNotMatch(source,/(?<![-\w])(?:font-size|line-height|font-weight)\s*:\s*[\d.]/,file);
    assert.doesNotMatch(source,/font(?:Size|Weight)|lineHeight|(?<![-\w])font\s*:\s*[\d.]/,file);
    for(const match of source.matchAll(/(?<![-\w])(?:font-size|line-height|font-weight)\s*:\s*([^;}\n]+)/g))
      assert.ok(match[1].startsWith('var(--ui-') || match[1]==='inherit',file+': '+match[0]);
    const outsideRoot=file==='admin.css'?source.replace(/:root\s*\{[^}]*\}/g,''):source;
    assert.doesNotMatch(outsideRoot,/--ui-[\w-]*(?:size|line|weight[\w-]*)\s*:/,file);
  }
  for(const match of css.matchAll(/@media[^{}]*\{/g)) {
    let depth=1,end=match.index+match[0].length;
    for(;depth && end<css.length;end++)depth+=(css[end]==='{')-(css[end]==='}');
    assert.doesNotMatch(css.slice(match.index+match[0].length,end),/font-size|line-height|font-weight|font:/);
  }
});
