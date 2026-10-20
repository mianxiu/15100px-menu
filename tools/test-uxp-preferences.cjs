const assert=require('node:assert/strict');
const labels=require('../uxp/offline-probe/labels.js');
(async()=>{
 let name='kPanelBrightnessLightGray',font=3,calls=[];
 const ps={app:{preferences:{interface:{get textFontSize(){return font;}}}},
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
 console.log('UXP interface preferences: four themes, three sizes, unavailable retention, read-only get passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
