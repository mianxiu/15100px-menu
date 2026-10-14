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
 console.log('UXP interface preferences: four themes, three sizes, unavailable retention, read-only get passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
