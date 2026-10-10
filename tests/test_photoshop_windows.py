import unittest
from types import SimpleNamespace
from backend.photoshop_windows import workspace_root


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.names = {1:'Photoshop',2:'OWL.DocumentWindow',3:'OWL.Dock',4:'#32770',
                      5:'OtherApp',6:'OWL.DocumentWindow',7:'Edit',8:'OWL.ShadowView'}
        self.visible = self.enabled = set(self.names)
        self.enabled = set(self.names)
        self.gui = SimpleNamespace(IsWindow=lambda h:h in self.names,
            IsIconic=lambda h:False, GetAncestor=lambda h,mode:(2 if h==7 else h) if mode==2 else 1,
            GetClassName=lambda h:self.names[h], IsWindowVisible=lambda h:h in self.visible,
            IsWindowEnabled=lambda h:h in self.enabled)
        self.pid = lambda h: 99 if h==6 else 10

    def test_main_floating_document_panel_and_input_share_workspace(self):
        for h in (1,2,3,7):
            self.assertEqual(workspace_root(self.gui,h,self.pid),1)

    def test_dialog_foreign_process_shadow_and_other_app_are_rejected(self):
        for h in (0,4,5,6,8):
            self.assertEqual(workspace_root(self.gui,h,self.pid),0)

    def test_modal_disabled_main_blocks_floating_workspace(self):
        self.enabled.remove(1)
        for h in (1,2,3,7):
            self.assertEqual(workspace_root(self.gui,h,self.pid),0)

    def test_hidden_or_disabled_floating_window_is_rejected(self):
        self.visible.remove(2)
        self.assertEqual(workspace_root(self.gui,2,self.pid),0)
        self.enabled.remove(3)
        self.assertEqual(workspace_root(self.gui,3,self.pid),0)
