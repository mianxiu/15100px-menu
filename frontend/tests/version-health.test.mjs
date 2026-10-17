import {test} from 'node:test';
import assert from 'node:assert/strict';
import {healthView,healthFinding} from '../src/version-health.mjs';
import {translate} from '../src/i18n.mjs';
test('warnings persist until acknowledged; new report can reopen the notice',()=>{
 assert.equal(healthView().alert,false);
 assert.equal(healthView({attention:true}).alert,true);
 assert.equal(healthView({attention:true,acknowledged:true}).alert,false);
 assert.equal(healthView({attention:true,acknowledged:false}).alert,true);
});
test('unknown capability never becomes proof of preview support',()=>{
 assert.match(healthFinding('redraw_capability_unreported'),/待核验/);
 assert.match(healthFinding('legacy_preview_pending'),/尚待修复/);
 assert.equal(healthFinding('untrusted document title'),'未知兼容性线索，请导出报告');
 assert.deepEqual(healthView({findings:{secret:true}}).findings,[]);
});
test('new background checks and findings have English labels',()=>{
 for(const code of ['redraw_api_missing','plugin_not_ready','status_unavailable','legacy_preview_pending','task_failed'])
  assert.notEqual(translate(healthFinding(code),'en'),healthFinding(code));
 assert.equal(translate('版本变化自动自检','en'),'Automatic version checks');
});
