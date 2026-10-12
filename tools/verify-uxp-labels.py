"""Use COM only for scratch-document setup/readback; all label writes use UXP."""
import json
import os
import secrets
from pathlib import Path
import time
from urllib.request import urlopen
import win32com.client
from uxp_label_client import Client

status=json.load(urlopen('http://127.0.0.1:15151/api/status',timeout=3))
assert not status['photoshop']['busy'], 'Production operation is running'
app=win32com.client.GetActiveObject('Photoshop.Application')
client=Client()
name='UXP label verification '+str(time.time_ns())
previous=app.ActiveDocument if app.Documents.Count else None
scratch=None
results=[]
try:
    app.DoJavaScript('app.documents.add(32,32,72,'+json.dumps(name)+',NewDocumentMode.RGB,DocumentFill.TRANSPARENT);')
    scratch=app.ActiveDocument
    target=client.call('capture')['target']
    read="(function(){var s=stringIDToTypeID,r=new ActionReference();r.putEnumerated(s('layer'),s('ordinal'),s('targetEnum'));return typeIDToStringID(executeActionGet(r).getEnumerationValue(s('color')));})();"
    for color in ('red','orange','yellowColor','grain','blue','violet','gray','none'):
        response=client.call('set_label',target=target,color=color)
        assert app.DoJavaScript(read)==color, 'Independent color readback failed'
        results.append(response)
    for changed in ({**target,'document_id':target['document_id']+999},
                    {**target,'session':'stale'}, {**target,'layer_ids':[]}):
        try: client.call('set_label',target=changed,color='red')
        except RuntimeError: pass
        else: raise AssertionError('Changed target was accepted')
        assert app.DoJavaScript(read)=='none'
    app.DoJavaScript("app.activeDocument.artLayers.add();var s=stringIDToTypeID,r=new ActionReference(),d=new ActionDescriptor();r.putIdentifier(s('layer'),"+str(target['layer_ids'][0])+");d.putReference(s('null'),r);d.putEnumerated(s('selectionModifier'),s('selectionModifierType'),s('addToSelection'));d.putBoolean(s('makeVisible'),false);executeAction(s('select'),d,DialogModes.NO);")
    multi=client.call('capture')['target']
    assert len(multi['layer_ids'])==2
    for color in ('blue','none'):
        results.append(client.call('set_label',target=multi,color=color))
        script="(function(){var s=stringIDToTypeID,ids="+json.dumps(multi['layer_ids'])+",out=[];for(var i=0;i<ids.length;i++){var r=new ActionReference();r.putIdentifier(s('layer'),ids[i]);out.push(typeIDToStringID(executeActionGet(r).getEnumerationValue(s('color'))));}return out.join(',');})();"
        assert app.DoJavaScript(script)==','.join([color]*2)
    expired_id=secrets.token_hex(16)
    expired={'id':expired_id,'token':client.token,'operation':'set_label','color':'red',
             'target':multi,'expires_at_ms':int(time.time()*1000)-1}
    temporary=client.folder/'expired-test.tmp'
    temporary.write_text(json.dumps(expired),'utf-8')
    os.replace(temporary,client.folder/'probe-request.json')
    time.sleep(.8)
    assert json.loads((client.folder/'probe-response.json').read_text('utf-8'))['id']!=expired_id
    assert app.DoJavaScript(script)=='none,none'
    assert client.call('inspect')['phase']=='completed'
    Path('.runtime/uxp-labels-physical-verification.json').write_text(json.dumps({
        'verified_at':time.time(),'label_results':results,'changed_targets_rejected':3,
        'multi_selection_count':2,
        'expired_request_ignored':True,
        'scope':'scratch single and multi-layer label writes; production menu not yet connected'},indent=2),'utf-8')
    print('PASS: eight labels, multi-layer blue/clear, independent readback, three target rejections')
finally:
    if scratch is not None:
        app.ActiveDocument=scratch
        assert app.ActiveDocument.Name==name
        app.DoJavaScript('app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);')
    if previous is not None: app.ActiveDocument=previous
