"""Read-only target snapshots and in-call JSX checks shared by all commands."""
import json


READ_TARGET_JS = """function __menuReadTarget() {
    if (!app.documents.length) throw new Error('目标文档已关闭，操作已取消');
    var s=stringIDToTypeID, r=new ActionReference();
    r.putProperty(s('property'),s('targetLayersIDs'));
    r.putEnumerated(s('document'),s('ordinal'),s('targetEnum'));
    var list=executeActionGet(r).getList(s('targetLayersIDs')), ids=[];
    for (var i=0;i<list.count;i++) ids.push(list.getReference(i).getIdentifier());
    if (!ids.length) throw new Error('请先选择图层');
    ids.sort(function(a,b){return a-b;});
    return {document_id:app.activeDocument.id,active_layer_id:app.activeDocument.activeLayer.id,layer_ids:ids};
}
"""
CAPTURE_SCRIPT = '(function(){' + READ_TARGET_JS + """
    var t=__menuReadTarget();
    return '{"document_id":'+t.document_id+',"active_layer_id":'+t.active_layer_id+',"layer_ids":['+t.layer_ids.join(',')+']}';
}());"""


def validate_target(value):
    if not isinstance(value, dict):
        raise ValueError('无法读取操作目标，未执行操作')
    doc, active, layers = value.get('document_id'), value.get('active_layer_id'), value.get('layer_ids')
    if (type(doc) is not int or doc <= 0 or type(active) is not int or active <= 0
            or not isinstance(layers, list) or not layers
            or any(type(layer) is not int or layer <= 0 for layer in layers)
            or len(set(layers)) != len(layers) or active not in layers):
        raise ValueError('无法读取有效文档／图层目标，未执行操作')
    return {'document_id':doc, 'active_layer_id':active, 'layer_ids':sorted(layers)}


def guarded_script(script, target):
    expected = json.dumps(validate_target(target), separators=(',', ':'))
    # No selection restoration: a changed target must cancel without mutation.
    return '(function(){' + READ_TARGET_JS + '\nvar expected=' + expected + ";" + """
    var actual=__menuReadTarget();
    if (actual.document_id!==expected.document_id)
        throw new Error('目标文档已改变，操作已取消；不会改用当前文档');
    if (actual.active_layer_id!==expected.active_layer_id || actual.layer_ids.join(',')!==expected.layer_ids.join(','))
        throw new Error('目标图层或选择已改变，操作已取消');
}());\n""" + script
