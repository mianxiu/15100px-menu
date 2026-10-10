"""Allow only verified Photoshop workspace windows, never owned dialogs."""
def workspace_root(gui, hwnd, process_id=None):
    if not hwnd or not gui.IsWindow(hwnd) or gui.IsIconic(hwnd):
        return 0
    top = gui.GetAncestor(hwnd, 2)
    name = gui.GetClassName(top)
    if name not in ('Photoshop', 'OWL.DocumentWindow', 'OWL.Dock'):
        return 0
    root = top if name == 'Photoshop' else gui.GetAncestor(top, 3)
    if not root or not gui.IsWindow(root) or gui.GetClassName(root) != 'Photoshop':
        return 0
    if gui.IsIconic(root) or not gui.IsWindowVisible(root) or not gui.IsWindowEnabled(root):
        return 0
    if not gui.IsWindowVisible(top) or not gui.IsWindowEnabled(top):
        return 0
    if process_id is None:
        import win32process
        process_id = lambda window: win32process.GetWindowThreadProcessId(window)[1]
    return root if process_id(top) == process_id(root) else 0
