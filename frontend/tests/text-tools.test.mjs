import {test} from 'node:test';
import assert from 'node:assert/strict';
import {replacePreview,splitPreview,defaultGroups} from '../src/text-tools.mjs';

test('literal preview handles CR/LF, emoji, adjacent matches and replacement literals',()=>{
  assert.deepEqual(replacePreview('猫猫\r😀','猫','$&'),{text:'$&$&\r😀',count:2});
  assert.deepEqual(replacePreview('a\rb','a\nb','x\ny'),{text:'x\ry',count:1});
  assert.deepEqual(replacePreview('aaa','aa','x'),{text:'xa',count:1});
  assert.deepEqual(replacePreview('abc','','x'),{text:'abc',count:0});
  assert.deepEqual(replacePreview('ABC','abc','x'),{text:'ABC',count:0});
});

test('line groups cover exact UTF-16 offsets and retain blank-line spacing',()=>{
  const text='猫\r😀\r\r尾';
  assert.equal(defaultGroups(text),'1,2,3,4');
  assert.deepEqual(splitPreview(text,'1-2，3-4'),{breaks:[5,7],groups:['猫\r😀','\r尾'],error:''});
  assert.deepEqual(splitPreview('A\r\rB','1,2,3').groups,['A','B']);
  assert.deepEqual(splitPreview('A\rB\r','1,2,3').breaks,[2,4]);
  for(const expression of ['2,1','1,3','1-2,2-4','1-5','1','1-4','0-4','1-2,3-4,'])assert.ok(splitPreview(text,expression).error,expression);
  assert.equal(splitPreview(text,'1-2,3-4').error,'');
  const many=Array.from({length:1000},()=> 'x').join('\r');assert.equal(splitPreview(many,defaultGroups(many)).error,'');
});
