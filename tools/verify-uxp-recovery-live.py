"""Inject a missing response read against real UXP on our disposable document.

This uses the production bridge and actual plugin, not physical hotkey gestures.
Only receipt reads are hidden; every modifying request is published once.
"""
import asyncio
import json
from pathlib import Path
import shutil
import sys
import time
from urllib.request import urlopen
from unittest.mock import patch
import win32com.client

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.uxp_bridge import UxpBridge,UxpResultUnknown,publish_request
from backend.version import APP_VERSION

async def main():
    status=json.load(urlopen('http://127.0.0.1:15151/api/status',timeout=5))
    assert status['version']==APP_VERSION and not status['photoshop']['busy']
    assert status['photoshop']['uxp_version']==json.loads((ROOT/'uxp/offline-probe/manifest.json').read_text('utf-8'))['version']
    folder=ROOT/('.runtime/recovery-'+APP_VERSION+'-live');folder.mkdir(exist_ok=True)
    config=folder/'uxp-config.json'
    shutil.copy2(Path(status['data_dir'])/'uxp-config.json',config)
    app=win32com.client.GetActiveObject('Photoshop.Application')
    previous=app.ActiveDocument if app.Documents.Count else None
    app.DoJavaScript('app.documents.add(32,32,72,"UXP recovery disposable",NewDocumentMode.RGB,DocumentFill.TRANSPARENT);')
    scratch=app.ActiveDocument
    bridge=UxpBridge(folder/'tasks.json',config)
    bridge.operation_timeout=2
    bridge.transport.response_timeout=.08
    evidence=[]
    try:
        for action,restart,frozen in [('label.red',False,False),('layer.new',True,False),('adjustment.curves',True,True)]:
            bridge.operation_timeout=2
            bridge.transport.response_timeout=10
            before=int(app.DoJavaScript('app.activeDocument.layers.length'))
            binding=bridge.transport.call('capture')['target'] if frozen else None
            read=bridge.transport.pending.read_result
            original_call=bridge.transport.call
            def injected_call(operation,**payload):
                previous_timeout=bridge.transport.response_timeout
                bridge.transport.response_timeout=.08 if operation in ('set_label','new_document') else 10
                try:return original_call(operation,**payload)
                finally:bridge.transport.response_timeout=previous_timeout
            with patch.object(bridge.transport,'call',side_effect=injected_call),patch.object(bridge.transport.pending,'read_result',return_value=None),patch('backend.uxp_bridge.publish_request',wraps=publish_request) as publication:
                try:await bridge.execute(action,frozen_target=binding)
                except UxpResultUnknown:pass
                else:raise AssertionError('Injected missing result must be unknown')
                task=bridge.tasks.snapshot()['items'][0]
                pending=dict(bridge.transport.pending.value)
                wire=Path(pending['folder'])/'probe-request.json'
                original=wire.read_bytes()
                for _ in range(3):assert (await bridge.reconcile_result())['active']
                try:await bridge.execute('label.blue')
                except RuntimeError:pass
                else:raise AssertionError('Unknown result accepted a new task')
                assert publication.call_count==(1 if frozen else 2), 'Optional read-only capture plus exactly one mutation'
                assert wire.read_bytes()==original
            deadline=time.monotonic()+5
            while read() is None and time.monotonic()<deadline:await asyncio.sleep(.05)
            assert read() is not None,'Actual plugin final receipt missing'
            if restart:
                await bridge.close()
                bridge=UxpBridge(folder/'tasks.json',config)
                assert bridge.busy and bridge.tasks.get(task['id'])['restored']
            with patch.object(bridge.transport,'call',side_effect=AssertionError('Recovery must only read files')):
                result=await bridge.reconcile_result()
            assert not result['active'] and not bridge.busy
            confirmed=bridge.tasks.get(task['id'])
            assert confirmed['state']=='succeeded' and confirmed['reconciled']
            assert wire.read_bytes()==original
            after=int(app.DoJavaScript('app.activeDocument.layers.length'))
            if action=='label.red':
                actual=app.DoJavaScript("(function(){var s=stringIDToTypeID,r=new ActionReference();r.putEnumerated(s('layer'),s('ordinal'),s('targetEnum'));return typeIDToStringID(executeActionGet(r).getEnumerationValue(s('color')));})();")
                assert actual=='red' and after==before
            else:
                assert after==before+1
                app.DoJavaScript('app.activeDocument.activeHistoryState=app.activeDocument.historyStates[app.activeDocument.historyStates.length-2];')
                assert int(app.DoJavaScript('app.activeDocument.layers.length'))==before
            evidence.append({'action':action,'task_id':task['id'],'request_id':pending['id'],'state':confirmed['state'],
                'restart':restart,'frozen_single_menu':frozen,'mutation_publications':1,'readback':True,'request_slot_unchanged':True})
        report={'version':APP_VERSION,'plugin':status['photoshop']['uxp_version'],'cases':evidence,
                'scope':'Real Photoshop/UXP on disposable document; simulated loss of backend receipt reads. Does not simulate a physical network disconnect or physical menu gestures.'}
        (ROOT/('.runtime/recovery-'+APP_VERSION+'-photoshop-live.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report))
    finally:
        await bridge.close()
        app.ActiveDocument=scratch
        app.DoJavaScript('app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);')
        if previous is not None:app.ActiveDocument=previous

asyncio.run(main())
