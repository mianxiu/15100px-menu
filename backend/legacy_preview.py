"""One explicit native execution channel; never a fallback for unknown UXP."""
import json
from .paths import ROOT


def returned_result(value, request):
    """Only a matching, normally returned script result proves COM execution exit."""
    try:
        if not isinstance(value,str) or len(value)>65536:return False
        result=json.loads(value)
        return (isinstance(result,dict) and result.get('schema')==1 and
                result.get('phase') in ('completed','failed') and
                all(result.get(k)==request[k] for k in ('id','session','operation','token')))
    except (ValueError,KeyError,TypeError):return False


def invoke(application, folder, request, prepared):
    if any(prepared.get(k) != request.get(k) for k in ('id', 'session', 'operation')):
        raise ValueError('Legacy prepare identity mismatch')
    if prepared.get('token') != request.get('token') or prepared.get('phase') != 'prepared':
        raise ValueError('Legacy prepare authentication mismatch')
    value = {**request, 'folder':str(folder), 'prepared':prepared['prepared']}
    source = (ROOT/'jsx/legacy_shape_preview.jsx').read_text('utf-8')
    # JSON is inserted as data; ensure_ascii also escapes JS line separators.
    script = source.replace('__PS_MENU_LEGACY_REQUEST__', json.dumps(value, ensure_ascii=True))
    return application.DoJavaScript(script)
