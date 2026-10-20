"""Read-side reuse never authorizes writes or renews snapshot freshness."""
import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from backend.uxp_bridge import UxpTransport,UxpBridge

class ObservationCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.transport=UxpTransport(self.root/'config.json');self.transport.storage=self.root/'PHSP'
        self.folder=self.host('24')
    def tearDown(self):self.temp.cleanup()
    def host(self,name,session='s',age=0):
        folder=self.transport.storage/name/'External/com.15100px.menu.offline-probe/PluginData';folder.mkdir(parents=True,exist_ok=True)
        (folder/'probe-last.json').write_text(json.dumps({'session':session,'probe_version':'0.3.48',
            'photoshop_version':'24.2.0','plugin_time_ms':time.time()*1000-age}),'utf-8')
        return folder
    def test_read_binding_reuses_discovery_but_writes_always_detect_second_host(self):
        with patch('backend.uxp_bridge.time.monotonic',return_value=100),patch.object(self.transport,'_discover',wraps=self.transport._discover) as discover:
            for _ in range(50):self.assertEqual(self.transport.observe()[0],self.folder)
            self.assertEqual(discover.call_count,1)
            self.host('25')
            with self.assertRaisesRegex(RuntimeError,'多个'):_=self.transport.folder
            self.assertEqual(discover.call_count,2)
        with patch('backend.uxp_bridge.time.monotonic',return_value=101):
            with self.assertRaisesRegex(RuntimeError,'多个'):self.transport.observe()
    def test_binding_reads_new_session_and_rejects_expired_lease(self):
        with patch('backend.uxp_bridge.time.monotonic',return_value=100):
            self.transport.observe();self.host('24',session='new')
            self.assertEqual(self.transport.observe()[1]['session'],'new')
            self.host('24',age=60000)
            with self.assertRaises(RuntimeError):self.transport.observe()
    def test_unchanged_layer_file_is_parsed_once_but_age_is_checked_every_time(self):
        bridge=UxpBridge(self.root/'tasks.json',self.root/'config.json');bridge.transport=self.transport
        source=self.folder/'layer-context.json'
        value={'schema':1,'session':'s','document_id':1,'layer_ids':[2],'kind':'pixel','mask':15,'quick_mask':127,'plugin_time_ms':time.time()*1000}
        source.write_text(json.dumps(value),'utf-8');read=Path.read_text;layer_reads=[]
        def counted(path,*args,**kwargs):
            if path==source:layer_reads.append(path)
            return read(path,*args,**kwargs)
        try:
            with patch.object(Path,'read_text',counted):
                for _ in range(50):self.assertEqual(bridge.read_layer_context()['mask'],15)
                self.assertEqual(len(layer_reads),1)
                bridge.layer_context['layer_ids'].clear()
                self.assertEqual(bridge.read_layer_context()['layer_ids'],[2])
                with patch('backend.layer_context.time.time',return_value=time.time()+3):
                    self.assertEqual(bridge.read_layer_context()['mask'],0)
                self.assertEqual(len(layer_reads),1)
                value['mask']=2;source.write_text(json.dumps(value),'utf-8')
                self.assertEqual(bridge.read_layer_context()['mask'],2);self.assertEqual(len(layer_reads),2)
                self.host('24',session='new')
                self.assertEqual(bridge.read_layer_context()['mask'],0)
        finally:bridge.executor.shutdown(wait=True)
