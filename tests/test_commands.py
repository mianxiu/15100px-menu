import unittest
from unittest.mock import Mock

from backend.commands import COMMANDS, REGISTRY, command_contracts, validate_command
from backend.main import Application
from backend.photoshop_bridge import PhotoshopBridge


class CommandTests(unittest.IsolatedAsyncioTestCase):
    def test_contracts_cover_every_existing_command(self):
        self.assertEqual(set(REGISTRY), set(COMMANDS))
        self.assertEqual(len(REGISTRY), 12)
        for contract in command_contracts():
            self.assertEqual(contract['version'], 1)
            self.assertEqual(contract['channel'], 'com-jsx')
            self.assertIn('not-busy', contract['conditions'])
            self.assertTrue(contract['recovery'])
        self.assertIn('read-back', REGISTRY['label.none'].expected_result)
        self.assertIn('not-verified', REGISTRY['select'].expected_result)

    async def test_invalid_parameters_rejected_before_menu_or_com(self):
        app = Mock()
        for params in ({'unexpected': 1}, [], 'text', 1):
            with self.assertRaisesRegex(ValueError, '不接受参数'):
                await Application.dispatch(app, 'action.execute', {'name': 'select', 'params': params})
        app.desktop.require_action_focus.assert_not_called()
        app.bridge.execute.assert_not_called()

    async def test_registry_can_be_read_without_photoshop(self):
        result = await Application.dispatch(Mock(), 'commands.list', {})
        self.assertEqual(len(result['commands']), 12)

    async def test_bridge_rejects_unknown_before_com(self):
        bridge = PhotoshopBridge()
        bridge._application = Mock(side_effect=AssertionError('COM must not run'))
        try:
            for name in (None, [], 'unknown'):
                with self.assertRaisesRegex(ValueError, '未知'):
                    await bridge.execute(name)
            bridge._application.assert_not_called()
        finally:
            await bridge.close()

    def test_valid_empty_parameters_and_immutable_contract(self):
        self.assertIs(validate_command('select', {}), REGISTRY['select'])
        with self.assertRaises(TypeError):
            REGISTRY['unknown'] = REGISTRY['select']
