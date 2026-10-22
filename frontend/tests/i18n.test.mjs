import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {parse} from '@babel/parser';
import {translate} from '../src/i18n.mjs';
import english from '../src/locales/en.mjs';

test('default Chinese and English labels, unknown diagnostics stay verbatim',()=>{
  assert.equal(translate('插件管理'),'插件管理');
  assert.equal(translate('插件管理','en'),'Plugins');
  assert.equal(translate('已清除 2 个图层的标签，并核验为无颜色','en'),'Cleared labels on 2 layers; verified no color');
  assert.equal(translate('My document.psd','en'),'My document.psd');
});
test('every static interface translation has an English entry',()=>{
  const trees=['index.jsx'].map(name=>parse(readFileSync(new URL('../src/'+name,import.meta.url),'utf8'),{sourceType:'module',plugins:['jsx']}));
  let count=0;
  function visit(node){
    if(!node || typeof node!=='object')return;
    if(node.type==='CallExpression'&&node.callee.name==='t'&&node.arguments[0]?.type==='StringLiteral'){
      const key=node.arguments[0].value;assert.ok(Object.hasOwn(english,key),key);count++;
    }
    for(const value of Object.values(node))if(Array.isArray(value))value.forEach(visit);else if(value&&typeof value==='object')visit(value);
  }
  trees.forEach(visit);assert.ok(count>150);
});
