"""One explicit native execution channel; never a fallback for unknown UXP."""
import json
from .paths import ROOT


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
