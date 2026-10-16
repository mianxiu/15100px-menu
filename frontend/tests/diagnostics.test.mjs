import {test} from 'node:test';
import assert from 'node:assert/strict';
import {diagnosticClock,diagnosticScopes,diagnosticFinding} from '../src/diagnostics.mjs';

test('scoped checks and uncertain loader evidence are explicit',()=>{
 assert.deepEqual(diagnosticScopes.map(row=>row[0]),['all','menu','uxp','runtime']);
 assert.match(diagnosticFinding('uxp_user_external_scan_not_observed'),/尚非故障根因/);
 assert.equal(diagnosticFinding('untrusted secret'),'检测结果待核对');
 assert.equal(diagnosticClock({phase:'collecting',stage:'uxp',message:'uxp',remaining_ms:0},10).label,'uxp');
});
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
