import asyncio,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from backend.diagnostics import Diagnostics

class DiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_is_single_job_and_export_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Diagnostics(folder,'probe.ps1',15153);gate=asyncio.Event()
            async def collect():await gate.wait()
            with patch.object(d,'collect',collect):
                self.assertEqual(d.start()['phase'],'collecting')
                with self.assertRaises(RuntimeError):d.start()
                with self.assertRaises(RuntimeError):d.export()
                await d.close();self.assertTrue(d.task.cancelled())
    async def test_subprocess_failure_is_not_a_ready_report(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Diagnostics(folder,'probe.ps1',15153)
            with patch('asyncio.create_subprocess_exec',side_effect=OSError('not installed')):
                d.start();await d.task
            self.assertEqual(d.snapshot()['phase'],'failed');self.assertFalse(d.snapshot()['ready'])
            with self.assertRaises(RuntimeError):d.export()
