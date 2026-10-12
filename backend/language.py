"""UI language preference, separate from native input settings."""
import json
from pathlib import Path
from .settings import atomic_json

LANGUAGES = ('zh-CN', 'en')
PLUGIN_NAMES = {'zh-CN':'Photoshop 快捷菜单', 'en':'Photoshop Quick Menu'}
COMMAND_NAMES = {'zh-CN':'检查连接', 'en':'Check connection'}

def plugin_name(language, version):
    return f'{PLUGIN_NAMES[language]} v{version}'

def read_language(runtime):
    path=Path(runtime)/'ui-language.json'
    if not path.exists():return 'zh-CN'
    value=json.loads(path.read_text('utf-8')).get('language')
    if value not in LANGUAGES:raise ValueError('不支持的界面语言')
    return value

def save_language(runtime, language):
    if language not in LANGUAGES:raise ValueError('不支持的界面语言')
    atomic_json(Path(runtime)/'ui-language.json',{'language':language})

def localized_manifest(data, language):
    # Explicit preference, independent of Photoshop's own display language.
    data=json.loads(json.dumps(data))
    data['name']=plugin_name(language, data['version'])
    for item in data['entrypoints']:
        if item['id']=='probe':item['label']={'default':COMMAND_NAMES[language]}
    return data
