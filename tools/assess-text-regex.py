"""Offline fixed-input regex risk check; never connects to Photoshop."""
from pathlib import Path
import json,subprocess,time
r=Path.cwd();rows=[]
cases=[('literal',"const s='a'.repeat(30)+'!';const t=performance.now();for(let i=0;i<10000;i++)s.indexOf('a');console.log(JSON.stringify({ms:performance.now()-t,iterations:10000}));"),
       ('linear-regex',"const s='a'.repeat(30)+'!';const t=performance.now();const result=/^a+$/.test(s);console.log(JSON.stringify({ms:performance.now()-t,result}));"),
       ('nested-backtracking',"console.log('started');setTimeout(()=>{console.log('timer-fired');process.exit(2);},10);const t=performance.now();const result=/^(a+)+$/.test('a'.repeat(30)+'!');console.log(JSON.stringify({ms:performance.now()-t,result}));")]
for name,script in cases:
 started=time.perf_counter()
 try:
  result=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=.5,creationflags=0x08000000|0x00004000,check=True)
  rows.append({'case':name,'wall_ms':(time.perf_counter()-started)*1000,'timed_out':False,'stdout':result.stdout.strip()})
 except subprocess.TimeoutExpired as error:
  stdout=(error.stdout or b'').decode('utf-8') if isinstance(error.stdout,bytes) else error.stdout or ''
  rows.append({'case':name,'wall_ms':(time.perf_counter()-started)*1000,'timed_out':True,'deadline_ms':500,'stdout':stdout.strip(),'only_owned_helper_terminated':True})
assert rows[-1]['timed_out'] and rows[-1]['stdout']=='started',rows
report={'scope':'offline Node evaluator only; no Photoshop connection or user text','rows':rows,'decision':'Do not execute unrestricted regex on UXP/browser event loop; separate cancellable computation required before a regex product feature.'}
(r/'.runtime').mkdir(exist_ok=True)
(r/'.runtime/text-regex-assessment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report))
