"""Native Photoshop label enums, separate from editable JSX script packages."""
import json

# Spellings are Action Manager enums, not UI names; the last four need PS25+.
LABEL_COLORS = [
    {"id": "none", "label": "无颜色", "rgb": [105, 109, 117]},
    {"id": "red", "label": "红色", "rgb": [224, 91, 88]},
    {"id": "orange", "label": "橙色", "rgb": [229, 151, 63]},
    {"id": "yellowColor", "label": "黄色", "rgb": [226, 201, 83]},
    {"id": "grain", "label": "绿色", "rgb": [110, 176, 99]},
    {"id": "blue", "label": "蓝色", "rgb": [88, 144, 213]},
    {"id": "violet", "label": "紫色", "rgb": [169, 125, 207]},
    {"id": "gray", "label": "灰色", "rgb": [169, 172, 180]},
    {"id": "seafoam", "label": "海沫色", "rgb": [93, 171, 164]},
    {"id": "indigo", "label": "靛蓝", "rgb": [112, 111, 188]},
    {"id": "magenta", "label": "洋红", "rgb": [189, 91, 157]},
    {"id": "fuchsia", "label": "紫红", "rgb": [211, 120, 184]},
]
LABEL_ACTIONS = {"label." + item["id"]: {"label": item["label"] + "图层标签"} for item in LABEL_COLORS}


def label_script(action):
    if action not in LABEL_ACTIONS:
        raise ValueError("未知的图层标签颜色")
    color = json.dumps(action.split(".", 1)[1])
    return """(function () {
        if (!app.documents.length) throw new Error('请先打开文档');
        var s = stringIDToTypeID;
        var color = %s;
        if (/^(seafoam|indigo|magenta|fuchsia)$/.test(color) && parseInt(app.version,10)<25) throw new Error('此标签颜色需要Photoshop2024或更新版本');
        var selected = [], wanted = {}, inherited = 0;
        var selection = new ActionReference();
        selection.putProperty(s('property'), s('targetLayersIDs'));
        selection.putEnumerated(s('document'), s('ordinal'), s('targetEnum'));
        var list = executeActionGet(selection).getList(s('targetLayersIDs'));
        for (var i=0; i<list.count; ++i) {
            var id = list.getReference(i).getIdentifier();
            selected.push(id); wanted[id] = true;
        }
        if (!selected.length) throw new Error('请先选择图层');
        function readColor(id) {
            var r = new ActionReference(); r.putIdentifier(s('layer'), id);
            return typeIDToStringID(executeActionGet(r).getEnumerationValue(s('color')));
        }
        var ref = new ActionReference();
        ref.putEnumerated(s('layer'), s('ordinal'), s('targetEnum'));
        var change = new ActionDescriptor();
        change.putEnumerated(s('color'), s('color'), s(color));
        var command = new ActionDescriptor();
        command.putReference(s('null'), ref);
        command.putObject(s('to'), s('layer'), change);
        executeAction(s('set'), command, DialogModes.NO);
        for (var j=0; j<selected.length; ++j) {
            if (readColor(selected[j]) !== color) throw new Error('标签结果校验失败，请检查图层状态；不会自动重试');
        }
        if (color === 'none') {
            function scan(layers, parentColor) {
                for (var k=0; k<layers.length; ++k) {
                    var layer=layers[k], group=layer.typename === 'LayerSet';
                    var own=(group || wanted[layer.id]) ? readColor(layer.id) : 'none';
                    if (wanted[layer.id] && own === 'none' && parentColor !== 'none') ++inherited;
                    if (group) scan(layer.layers, own !== 'none' ? own : parentColor);
                }
            }
            scan(app.activeDocument.layers, 'none');
        }
        return '{"verified":true,"count":'+selected.length+',"inherited":'+inherited+'}';
    }());""" % color
