"""Measure cached menu metadata and real UXP inspect transport on owned shapes.
No colour writes, synthesized input, document saves or user document edits.
"""
import asyncio,json,shutil,statistics,sys,time
from pathlib import Path
from urllib.request import urlopen
import win32com.client
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from backend.uxp_bridge import UxpBridge
from backend.shape_paint import metadata
from benchmark_read_helpers import fixture,summary

async def main():
 s=json.load(urlopen('http://127.0.0.1:15151/api/status'));assert not s['photoshop']['busy'] and not s['menu']['visible']
 app=win32com.client.GetActiveObject('Photoshop.Application');previous=app.ActiveDocument if app.Documents.Count else None
 folder=ROOT/'.runtime'/('shape-performance-'+str(time.time_ns()));folder.mkdir();config=folder/'uxp-config.json'
 shutil.copy2(Path(s['data_dir'])/'uxp-config.json',config);bridge=UxpBridge(folder/'tasks.json',config)
 cases=[];scratch=None
 try:
  for count in (4,100):
   app.DoJavaScript(fixture('shape',count));scratch=app.ActiveDocument
   # Large fixture creation pauses UXP. Wait only for fresh read-only heartbeat,
   # before publishing any request; never replay a submitted operation.
   deadline=time.monotonic()+5
   while True:
    try:bridge.transport.folder;break
    except RuntimeError:
     if time.monotonic()>=deadline:raise
     await asyncio.sleep(.05)
   samples={False:[],True:[]};data=None
   for i in range(15):
    for include in ((False,True) if i%2==0 else (True,False)):
     started=time.perf_counter();r=await asyncio.to_thread(bridge.transport.call,'inspect',shape_inspect=include)
     elapsed=(time.perf_counter()-started)*1000;assert r['phase']=='completed'
     if i>=3:samples[include].append(elapsed)
     if include:data=r['shape_editor'];assert data['available']
   cached=[]
   for _ in range(500):
    started=time.perf_counter();value=metadata(data);cached.append((time.perf_counter()-started)*1000);assert value['available']
   cases.append({'layers':count,'document_inspect_transport':summary(samples[False]),'shape_forced_inspect_transport':summary(samples[True]),
     'cached_menu_metadata_validation':summary(cached),'pattern_count':len(data['patterns'])})
   app.ActiveDocument=scratch;scratch.Close(2);scratch=None
  report={'observed_service_version':s['version'],'uxp':s['uxp']['version'],'cases':cases,
   'scope':'Alternating 12 measured pairs after 3 warm-ups, owned 4/100-node vector documents. Transport includes local file publication, plugin scheduling, inspect, target properties and response; not isolated batchPlay time. Cached path validates existing menu metadata without PS IPC. No edits.'}
  (ROOT/'.runtime/shape-read-performance128.json').write_text(json.dumps(report,indent=2),'utf-8')
  print(json.dumps(report),flush=True)
 finally:
  await bridge.close()
  if scratch:app.ActiveDocument=scratch;scratch.Close(2)
  if previous is not None:app.ActiveDocument=previous
asyncio.run(main())
