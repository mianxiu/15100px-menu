import copy,unittest
from backend.settings import DEFAULTS,validate

class RenderModeTests(unittest.TestCase):
    def test_legacy_settings_migrate_to_auto_without_changing_other_values(self):
        value=copy.deepcopy(DEFAULTS);del value['render_mode']
        self.assertEqual(validate(value),DEFAULTS)

    def test_modes_are_explicit_and_invalid_values_are_rejected(self):
        for mode in ('auto','gpu','cpu'):
            value=copy.deepcopy(DEFAULTS);value['render_mode']=mode
            self.assertEqual(validate(value)['render_mode'],mode)
        for mode in ('GPU','warp','',None,False):
            value=copy.deepcopy(DEFAULTS);value['render_mode']=mode
            with self.assertRaises(ValueError):validate(value)
