import copy,unittest,time
from backend.shape_paint import parameters,metadata
from backend.layer_context import validate,require_menu_target
from backend.desktop import shape_editor_allowed
from backend.mask_preview import MaskPreview
from backend.uxp_bridge import UxpBridge
from backend.tasks import TaskCancelled

class BatchMasks(unittest.TestCase):
    def setUp(self):
        self.shape={'available':True,'mask_batch':True,'revision':'s:batch:1','layer_ids':[3,8],'active_layer_id':8,'mask':{'feather':1,'density':80},'mixed':{'feather':True,'density':True},'live_preview':True,'preview_engine':'legacy-com'}
        self.context={'schema':1,'session':'s','document_id':2,'layer_ids':[3,8],'kind':'mixed','mask':15,'plugin_time_ms':time.time()*1000,'shape_editor':self.shape}
    def test_partial_parameters_never_supply_unedited_value_or_color(self):
        p={'mask_batch':True,'revision':'s:batch:1','mask':{'feather':12}}
        self.assertEqual(parameters(p),p);preview=MaskPreview(1,p)
        preview.update({**p,'mask':{'feather':13,'density':40}})
        self.assertEqual(preview.paint['mask'],{'feather':13,'density':40})
        for bad in ({}, {'density':101},{'feather':True},{'opacity':30}):
            with self.assertRaises(ValueError):parameters({**p,'mask':bad})
        with self.assertRaises(ValueError):parameters({**p,'fill':{}})
    def test_batch_editor_uses_exact_selection_and_rejects_stale_or_locked(self):
        self.assertTrue(metadata(self.shape)['available'])
        self.assertTrue(validate(self.context,'s')['shape_editor']['available'])
        self.assertTrue(shape_editor_allowed({'kind':'layers'},self.shape,True,self.context))
        require_menu_target(self.context,'shape.paint',self.context)
        for change in ({'layer_ids':[3,9]},{'locked':True},{'background':True}):
            value={**self.context,**change}
            self.assertFalse(validate(value,'s').get('shape_editor',{}).get('available',False))
            self.assertFalse(shape_editor_allowed({'kind':'layers'},self.shape,True,value))
            with self.assertRaises(TaskCancelled):require_menu_target(value,'shape.paint',value)
        for panel in ('home','canvas','text','unknown'):
            self.assertFalse(shape_editor_allowed({'kind':panel},self.shape,True,self.context))
        self.assertFalse(shape_editor_allowed({'kind':'layers','input_focused':True},self.shape,True,self.context))
    def test_bad_batch_metadata_cannot_enable_controls(self):
        for changes in ({'active_layer_id':True},{'active_layer_id':99},{'layer_ids':[3,3]},{'layer_ids':[8,3]},{'layer_ids':[3]}, {'mixed':{}},{'live_preview':'yes'},{'mask':{'feather':1}}):
            self.assertFalse(metadata({**self.shape,**changes})['available'])
    def test_frozen_active_layer_is_not_replaced_with_first_selected_id(self):
        bridge=object.__new__(UxpBridge);bridge.focus_guard=None
        target={'session':'s','document_id':2,'layer_ids':[3,8],'active_layer_id':8}
        self.assertEqual(bridge._bind_batch_mask_target(target)['active_layer_id'],8)
        self.assertEqual(bridge._captured_target,target)
        with self.assertRaises(ValueError):bridge._bind_menu_target(target)
        for changes in ({'active_layer_id':9},{'layer_ids':[3,3]},{'session':''},{'layer_ids':[8]}):
            with self.assertRaises(ValueError):bridge._bind_batch_mask_target({**target,**changes})
