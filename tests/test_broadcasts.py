import asyncio,json,unittest
from backend.broadcasts import StatusDelivery
from tornado.websocket import WebSocketClosedError


class Client:
    def __init__(self,slow=False):self.slow=slow;self.frames=[];self.futures=[];self.closed=False
    def write_message(self,payload):
        if self.closed:raise WebSocketClosedError()
        self.frames.append(json.loads(payload));f=asyncio.get_running_loop().create_future();self.futures.append(f)
        if not self.slow:f.set_result(None)
        return f
    def close(self,**kwargs):
        self.closed=True
        for f in self.futures:
            if not f.done():f.set_exception(WebSocketClosedError())


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_unread_browser_never_blocks_other_clients_or_operation_progress(self):
        slow=Client(True);fast=Client();clients={slow,fast};delivery=StatusDelivery(clients)
        for n in range(12):
            delivery.send({'type':'operation','busy':n<11,'sequence':n})
        self.assertTrue(slow.closed);self.assertNotIn(slow,clients)
        self.assertEqual(len(slow.frames),4)
        self.assertEqual([x['sequence'] for x in fast.frames],list(range(12)))
        self.assertFalse(fast.frames[-1]['busy']);await asyncio.sleep(0)
        self.assertFalse(delivery.pending)

    async def test_byte_bound_and_write_error_do_not_change_other_consumers(self):
        slow=Client(True);delivery=StatusDelivery({slow},max_bytes=70)
        delivery.send({'text':'x'*30});delivery.send({'text':'x'*30})
        self.assertTrue(slow.closed);await asyncio.sleep(0);self.assertFalse(delivery.pending)
        closed=Client();closed.close();fast=Client();delivery=StatusDelivery({closed,fast})
        delivery.send({'type':'status'});await asyncio.sleep(0)
        self.assertNotIn(closed,delivery.clients);self.assertEqual(len(fast.frames),1)

    async def test_completed_writes_free_capacity_and_disconnect_forgets_tracking(self):
        client=Client(True);delivery=StatusDelivery({client})
        for n in range(8):
            delivery.send({'n':n});client.futures[-1].set_result(None)
        self.assertFalse(client.closed);delivery.forget(client);await asyncio.sleep(0)
        self.assertFalse(delivery.pending)
