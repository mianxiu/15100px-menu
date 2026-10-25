"""Native Photoshop label enums, separate from editable JSX script packages."""
import json
from pathlib import Path
import re
import threading

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

THEME_NAMES = ('light', 'light-gray', 'dark-gray', 'dark')
SLOT_NAMES = ('None', 'Red', 'Orange', 'Yellow', 'Green', 'Blue', 'Violet', 'Gray',
              'Seafoam', 'Indigo', 'Magenta', 'Fuchsia')


def read_label_palette(text):
    """Read only named label entries; UIColors.txt is data, never executable code."""
    colors = {}
    for item, name in zip(LABEL_COLORS, SLOT_NAMES):
        for suffix, field in (('', 'rgb'), ('Disabled', 'disabled_rgb')):
            match = re.search(r'\bSlotColor'+name+suffix+r':\s*(\[\s*(?:\[[^\[\]]+\]\s*,?\s*){4}\])', text, re.I)
            if not match:continue
            values = json.loads(match[1])
            if (len(values)!=4 or any(len(row)!=4 or
                    any(type(v) is not int or not 0<=v<=255 for v in row[:3]) or
                    type(row[3]) not in (int,float) or row[3]!=1 for row in values)):
                raise ValueError('无效的Photoshop标签色表')
            colors.setdefault(item['id'], {})[field] = [row[:3] for row in values]
    if any(item['id'] not in colors or 'rgb' not in colors[item['id']] for item in LABEL_COLORS[:8]):
        raise ValueError('Photoshop标签色表不完整')
    return colors


def running_label_file(host_version):
    import win32api, win32gui, win32process
    from .photoshop_version import exe_version, version_tuple
    try:
        roots=[]
        win32gui.EnumWindows(lambda hwnd,_:roots.append(hwnd) if win32gui.GetClassName(hwnd)=='Photoshop' else None,None)
        if len(roots)!=1:raise OSError('无法确认唯一Photoshop工作区')
        pid=win32process.GetWindowThreadProcessId(roots[0])[1]
        handle=win32api.OpenProcess(0x410,False,pid)
        try:path=Path(win32process.GetModuleFileNameEx(handle,0))
        finally:handle.Close()
        if path.name.lower()!='photoshop.exe' or version_tuple(exe_version(path))!=version_tuple(host_version):
            raise OSError('Photoshop进程与当前执行插件不匹配')
    except win32api.error as error:raise OSError('Photoshop原生标签色表暂不可读') from error
    return path.parent/'Required'/'UIColors.txt'


class LabelPalette:
    def __init__(self, locate=None):
        self.locate=locate or running_label_file
        self._lock=threading.Lock()
        self.identity=None
        self.colors={}
        self.source='fallback'

    def refresh(self, status):
        host=status.get('photoshop_version')
        session=status.get('layer_context',{}).get('session')
        with self._lock:
            if status.get('connected') and isinstance(host,str) and isinstance(session,str):
                identity=(host,session)
                if identity!=self.identity:
                    self.identity=identity;self.colors={};self.source='fallback'
                    try:
                        with self.locate(host).open('rb') as stream:data=stream.read(1024*1024+1)
                        if len(data)>1024*1024:raise ValueError('Photoshop标签色表过大')
                        self.colors=read_label_palette(data.decode('utf-8-sig'))
                        self.source='host-ui-colors'
                    except (OSError,ValueError,TypeError,KeyError):pass
            colors=self.colors
        index=THEME_NAMES.index(status.get('ui_theme')) if status.get('ui_theme') in THEME_NAMES else 3
        result=[]
        for item in LABEL_COLORS:
            color=colors.get(item['id'],{})
            result.append({**item,'rgb':list(color.get('rgb',[item['rgb']]*4)[index]),
                           **({'disabled_rgb':list(color['disabled_rgb'][index])} if 'disabled_rgb' in color else {})})
        return result


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
