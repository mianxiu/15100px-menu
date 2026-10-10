"""Search and keyboard selection for the native action popup."""
ITEMS = (
    ("select", "选择组内图层", "选择 组 图层 select group layer"),
    ("color", "橙色图层标签", "颜色 橙色 标签 color orange label"),
    ("moveToTop", "移到顶部", "排序 上 顶部 top up"),
    ("moveToBottom", "移到底部", "排序 下 底部 bottom down"),
)


class MenuSelection:
    def __init__(self):
        self.names = [item[0] for item in ITEMS]
        self.index = 0

    @property
    def current(self):
        return self.names[self.index] if self.names else None

    def filter(self, query, shortcuts=None):
        words = query.casefold().split()
        shortcuts = shortcuts or {}
        self.names = [name for name,label,keywords in ITEMS
                      if all(word in f"{label} {keywords} {shortcuts.get(name,'')}".casefold() for word in words)]
        self.index = 0

    def move(self, direction):
        if self.names:
            self.index = (self.index + direction) % len(self.names)

    def select(self, name):
        if name in self.names:
            self.index = self.names.index(name)


def display_shortcut(value):
    names = {"tab":"Tab", "capslock":"CapsLock", "ctrl":"Ctrl", "alt":"Alt", "shift":"Shift", "esc":"Esc", "space":"Space"}
    return " + ".join(names.get(part,part.upper()) for part in value.split("+") if part)
