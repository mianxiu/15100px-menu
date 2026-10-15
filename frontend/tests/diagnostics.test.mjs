import {test} from 'node:test';
import assert from 'node:assert/strict';
import {diagnosticClock} from '../src/diagnostics.mjs';
test('countdown advances locally and zero never claims completion',()=>{
 const d={phase:'collecting',stage:'prepare',remaining_ms:5000,received_at:1000,message:'prepare'};
 assert.equal(diagnosticClock(d,1000).seconds,5);
 assert.equal(diagnosticClock(d,2200).seconds,4);
 assert.equal(diagnosticClock(d,9000).seconds,0);
 assert.equal(diagnosticClock(d,9000).label,'正在开始采集，请保持PS前台');
 assert.equal(diagnosticClock({...d,stage:'sampling'},9000).label,'正在等待采集结束，请保持PS前台');
 assert.equal(diagnosticClock({...d,phase:'failed'},1000).showSeconds,false);
 assert.equal(diagnosticClock({...d,phase:'completed'},1000).showSeconds,false);
});
