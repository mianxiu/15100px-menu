"""Read focused control metadata only; never read text, values or UIA names."""
PROPERTIES=(30002,30003,30008,30010,30020,30022,30033,30040,30043,30046,30048)
NON_INPUT=frozenset({50000,50001,50002,50005,50006,50007,50008,50009,50010,
                    50011,50012,50013,50014,50017,50018,50019,50020,50021,
                    50022,50023,50024,50026,50027,50028,50029,50031,50034,50035,
                    50036,50037,50038,50039,50040})
CONTAINERS=frozenset({50025,50030,50032,50033})


def control_state(row,pid,workspace=False,tool=None):
    if (type(row.get(30002)) is not int or row.get(30002)!=pid or type(row.get(30003)) is not int or
        row.get(30008) is not True or row.get(30010) is not True or row.get(30022) is not False):
        return 'unknown'
    kind=row.get(30003)
    if kind in (50003,50004,50016) or row.get(30040) is True:
        return 'input'
    for pattern,readonly in ((30043,30046),(30033,30048)):
        if row.get(pattern) is True and row.get(readonly) is not True:return 'input'
        if type(row.get(pattern)) is not bool:return 'unknown'
    if row.get(30040) is not False:return 'unknown'
    if kind in NON_INPUT:return 'non-input'
    if workspace and kind in CONTAINERS and isinstance(tool,dict):
        if type(tool.get('isModal')) is not bool or not isinstance(tool.get('classID'),str):return 'unknown'
        if tool['isModal']:return 'input'
        tool=tool['classID']
        if tool.endswith('Tool') and tool.isascii() and tool.isidentifier():return 'non-input'
    if workspace and kind in CONTAINERS and isinstance(tool,str):
        if 'type' in tool.casefold() or 'text' in tool.casefold():return 'input'
        if tool.endswith('Tool') and tool.isascii() and tool.isidentifier():return 'non-input'
    return 'unknown'


class FocusAccessibility:
    def __init__(self):
        import comtypes.client
        U=comtypes.client.GetModule('UIAutomationCore.dll')
        self.client=comtypes.client.CreateObject(U.CUIAutomation8,interface=U.IUIAutomation2)
        self.client.AutoSetFocus=False
        self.client.ConnectionTimeout=100;self.client.TransactionTimeout=100
        self.cache=self.client.CreateCacheRequest()
        for prop in PROPERTIES:self.cache.AddProperty(prop)

    def read(self):
        element=self.client.GetFocusedElementBuildCache(self.cache)
        return {prop:element.GetCachedPropertyValue(prop) for prop in PROPERTIES}
