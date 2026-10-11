"""Versioned command contracts shared by the API and COM execution path."""
from dataclasses import asdict, dataclass
from types import MappingProxyType

from .layer_labels import LABEL_ACTIONS


ACTIONS = {
    "select": {"label": "选择组内图层", "shortcut": "CapsLock+A"},
    "color": {"label": "橙色图层标签", "shortcut": "CapsLock+C"},
    "moveToTop": {"label": "移到顶部", "shortcut": "CapsLock+W"},
    "moveToBottom": {"label": "移到底部", "shortcut": "CapsLock+S"},
}
COMMANDS = {**ACTIONS, **LABEL_ACTIONS}


@dataclass(frozen=True)
class Command:
    id: str
    label: str
    expected_result: str
    version: int = 2
    channel: str = "com-jsx"
    conditions: tuple = ("photoshop-connected", "document-open", "action-focus", "not-busy")
    target_document: str = "captured-id; same-COM-instance; cancel-if-active-document-changed"
    target_layers: str = "captured-selection-ids-and-active-layer; cancel-if-changed"
    cancellation: str = "before-dispatch-only; running COM cannot be interrupted"
    recovery: str = "no-auto-retry; inspect Photoshop after timeout or failure"
    parameters: tuple = ()


REGISTRY = MappingProxyType({
    name: Command(name, info["label"],
                  "selected-layer-colors-read-back" if name in LABEL_ACTIONS else "script-returned; document-effect-not-verified")
    for name, info in COMMANDS.items()
})


def validate_command(name, params=None):
    if not isinstance(name, str) or name not in REGISTRY:
        raise ValueError("未知的图层操作")
    if params is not None and (not isinstance(params, dict) or params):
        raise ValueError("此命令不接受参数")
    return REGISTRY[name]


def command_contracts():
    return [asdict(command) for command in REGISTRY.values()]
