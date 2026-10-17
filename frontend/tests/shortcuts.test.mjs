import {test} from 'node:test';
import assert from 'node:assert/strict';
import {prefixOptions,triggerKeys,shortcutParts,triggerAllowed,changePrefix,changeTrigger,shortcutError,shortcutErrors} from '../src/shortcuts.mjs';

test('current bindings and noncanonical modifier order remain editable without loss',()=>{
  for(const value of ['capslock','esc','capslock+w','shift+capslock+s','ctrl+alt+f12','tab+a','capslock+tab+w','capslock+shift+w','f5','']){
    const parts=shortcutParts(value);
    assert.equal(shortcutError(value),'');
    assert.equal(shortcutError(changeTrigger(value,parts.key)),'');
  }
  assert.equal(prefixOptions.length,32);
  assert.equal(new Set(prefixOptions.map(option=>option.value)).size,32);
  assert.equal(triggerKeys.length,52);
});

test('incomplete prefix changes never silently choose an unrelated trigger',()=>{
  assert.equal(changePrefix('capslock','ctrl'),'ctrl+');
  assert.equal(shortcutError('ctrl+'),'请选择按键');
  assert.equal(changeTrigger('ctrl+','f8'),'ctrl+f8');
  assert.equal(changePrefix('capslock+w','shift+capslock'),'shift+capslock+w');
  assert.equal(changePrefix('capslock+w',''),'');
  assert.equal(changeTrigger('ctrl+f8',''),'');
  assert.notEqual(shortcutError('',true),'');
});

test('conflicts are order-independent; optional disabled keys do not conflict',()=>{
  assert.deepEqual(shortcutErrors({toggle:'capslock',hide:'esc',a:'',b:''}),{});
  const conflicts=shortcutErrors({a:'capslock+shift+w',b:'shift+capslock+w'});
  assert.equal(conflicts.a,'快捷键不能重复');
  assert.equal(conflicts.b,'快捷键不能重复');
  assert.deepEqual(shortcutErrors({a:'capslock+w',b:'shift+capslock+w'}),{});
});

test('trigger choices exclude duplicate prefixes, bare letters and invalid single modifiers',()=>{
  assert.equal(triggerAllowed('tab','tab'),false);
  assert.equal(triggerAllowed('ctrl','capslock'),false);
  assert.equal(triggerAllowed('','w'),false);
  assert.equal(triggerAllowed('','1'),false);
  for(const value of ['ctrl','ctrl+ctrl+w','capslock+capslock','tab+tab','a','1','ctrl+home'])assert.notEqual(shortcutError(value),'');
  for(const key of triggerKeys)for(const option of prefixOptions){
    const value=[option.value,key].filter(Boolean).join('+');
    assert.equal(shortcutError(value)==='',triggerAllowed(option.value,key),value);
  }
});
