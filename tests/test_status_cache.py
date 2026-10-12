import asyncio
import threading
import time
import unittest
from unittest.mock import Mock
from backend.photoshop_bridge import PhotoshopBridge


class StatusCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_blocked_status_returns_cache_and_coalesces_concurrent_reads(self):
        bridge=PhotoshopBridge();release=threading.Event()
        bridge.status_timeout=.015
        bridge._status=Mock(return_value={'connected':True,'document':'previous.psd','message':'connected'})
        try:
            first=await bridge.status()
            self.assertTrue(first['status_fresh']);self.assertTrue(first['status_updated_at'])
            bridge._status_tick-=6 # A genuinely stale cache must report waiting.
            def read():
                release.wait(3)
                return {'connected':True,'document':'next.psd','message':'connected'}
            bridge._status=Mock(side_effect=read)
            # Measure production scheduling, not IsolatedAsyncioTestCase's
            # per-future debug stack capture, which can dominate on Windows.
            loop=asyncio.get_running_loop();previous_debug=loop.get_debug()
            loop.set_debug(False)
            try:
                start=time.monotonic()
                results=await asyncio.gather(*(bridge.status(force=True) for _ in range(20)))
                elapsed=time.monotonic()-start
            finally:loop.set_debug(previous_debug)
            self.assertLess(elapsed,.5)
            bridge._status.assert_called_once()
            for item in results:
                self.assertEqual(item['document'],'previous.psd')
                self.assertEqual(item['status_wait_reason'],'status-read-pending')
                self.assertFalse(item['status_fresh'])
                self.assertEqual(item['status_updated_at'],first['status_updated_at'])
            release.set();await bridge._status_future
            latest=await bridge.status()
            self.assertEqual(latest['document'],'next.psd');self.assertTrue(latest['status_fresh'])
        finally:release.set();await bridge.close()

    async def test_recent_cache_remains_fresh_during_background_refresh(self):
        bridge=PhotoshopBridge();release=threading.Event()
        bridge.status_timeout=.01
        bridge._status=Mock(return_value={'connected':True,'document':'known.psd','message':'connected'})
        try:
            await bridge.status()
            def blocked():release.wait(3);return {'connected':True,'document':'new.psd'}
            bridge._status=Mock(side_effect=blocked)
            status=await bridge.status(force=True)
            self.assertTrue(status['status_read_pending'])
            self.assertTrue(status['status_fresh'])
            self.assertEqual(status['message'],'connected')
            bridge.busy=True
            self.assertFalse(bridge._status_snapshot()['status_fresh'])
            bridge.busy=False;bridge._status_tick-=6
            stale=bridge._status_snapshot()
            self.assertFalse(stale['status_fresh'])
            self.assertIn('状态等待更新',stale['message'])
        finally:release.set();await bridge.close()

    async def test_cancelled_request_does_not_cancel_shared_read(self):
        bridge=PhotoshopBridge();release=threading.Event();started=threading.Event()
        def read():started.set();release.wait(3);return {'connected':True,'document':'done.psd'}
        bridge._status=Mock(side_effect=read)
        pending=asyncio.create_task(bridge.status())
        try:
            while not started.is_set():await asyncio.sleep(.001)
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):await pending
            self.assertFalse(bridge._status_future.cancelled())
            result=await bridge.status(force=True)
            self.assertTrue(result['status_read_pending']);bridge._status.assert_called_once()
            release.set();await bridge._status_future
            self.assertEqual((await bridge.status())['document'],'done.psd')
        finally:release.set();await bridge.close()

    async def test_busy_never_queues_read_and_failed_read_retains_cache(self):
        bridge=PhotoshopBridge()
        bridge._status=Mock(return_value={'connected':True,'document':'known.psd'})
        try:
            await bridge.status()
            bridge.busy=True
            result=await bridge.status(force=True)
            self.assertEqual(result['status_wait_reason'],'operation-running')
            self.assertEqual(bridge._status.call_count,1)
            bridge.busy=False;bridge._status=Mock(side_effect=RuntimeError('temporary read failure'))
            result=await bridge.status(force=True)
            self.assertEqual(result['document'],'known.psd')
            self.assertEqual(result['status_wait_reason'],'status-read-failed')
            self.assertFalse(result['status_fresh'])
            await bridge.status();bridge._status.assert_called_once()
        finally:await bridge.close()
