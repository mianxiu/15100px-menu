const assert=require('node:assert/strict');
const labels=require('../uxp/offline-probe/labels.js');
(async()=>{
 let name='kPanelBrightnessLightGray',font=3,calls=[],fontReads=0;
 const ps={app:{preferences:{interface:{get textFontSize(){fontReads++;return font;}}}},
  constants:{FontSize:{SMALL:1,MEDIUM:2,LARGE:3}},
  action:{batchPlay:async descriptors=>{calls.push(descriptors);if(name==='throw')throw Error('modal');
   return [{interfacePrefs:{kuiBrightnessLevel:{_value:name}}}];}},
  core:{executeAsModal:()=>{throw Error('Preferences must stay read-only');}}};
 const read=labels(ps,'session').interfacePreferences;
 for(const [raw,theme] of Object.entries({kPanelBrightnessOriginal:'light',kPanelBrightnessLightGray:'light-gray',
  kPanelBrightnessMediumGray:'dark-gray',kPanelBrightnessDarkGray:'dark'})){
  name=raw;assert.equal((await read()).ui_theme,theme);
 }
 for(const [value,size] of [[1,'small'],[2,'medium'],[3,'large']]){font=value;assert.equal((await read()).ui_font_size,size);}
 name='unknown';font=99;assert.deepEqual(await read(),{ui_theme:'dark',ui_font_size:'large'});
 name='throw';assert.deepEqual(await read(),{ui_theme:'dark',ui_font_size:'large'});
 assert.ok(calls.every(ds=>ds.length===1 && ds[0]._obj==='get' && ds[0]._target[0]._property==='interfacePrefs'));
 const legacy=labels({...ps,app:{}},'legacy').interfacePreferences;name='kPanelBrightnessLightGray';
 assert.deepEqual(await legacy(),{ui_theme:'light-gray',ui_font_size:'small'});
 for(const stop of [1,2,3]){
  let checkpoints=0;const before=calls.length,interrupted=Error('interactive request');
  await assert.rejects(read(async()=>{if(++checkpoints===stop)throw interrupted;}),e=>e===interrupted);
  assert.equal(calls.length-before,stop===3?1:0,'A checkpoint must skip remaining host calls');
 }
 // Startup caches each successfully read field. Failure/interruption must
 // retry only the missing field, rather than freezing a default as success.
 const startup=labels(ps,'startup').interfacePreferences;name='throw';font=3;
 const fontsBefore=fontReads;
 const partial=await startup(null,true);
 assert.equal(partial.ui_preferences_complete,false);assert.equal(partial.ui_font_size,'large');
 assert.equal('ui_theme' in partial,false);
 name='kPanelBrightnessLightGray';const cached=await startup(null,true);
 assert.equal(cached.ui_preferences_complete,true);assert.equal(fontReads-fontsBefore,1);
 const callsBefore=calls.length;name='kPanelBrightnessOriginal';font=1;
 for(let n=0;n<12;n++)assert.deepEqual(await startup(null,true),cached);
 assert.equal(fontReads-fontsBefore,1);assert.equal(calls.length,callsBefore);
 const restarted=await labels(ps,'restarted').interfacePreferences(null,true);
 assert.equal(restarted.ui_theme,'light');assert.equal(restarted.ui_font_size,'small');
 const interrupted=labels(ps,'interrupted').interfacePreferences,stop=Error('new menu');
 let checkpoints=0;const fontAt=fontReads,themeAt=calls.length;
 await assert.rejects(interrupted(async()=>{if(++checkpoints===2)throw stop;},true),e=>e===stop);
 assert.equal(fontReads,fontAt+1);assert.equal(calls.length,themeAt);
 assert.equal((await interrupted(null,true)).ui_preferences_complete,true);
 assert.equal(fontReads,fontAt+1,'Retry must retain the successful font read');
 assert.equal(calls.length,themeAt+1);
 console.log('PASS startup preferences: once per field/session, partial failure retry, checkpoint retention, unchanged timestamp, new startup reread');
 console.log('UXP interface preferences: four themes, three sizes, unavailable retention, read-only get passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
