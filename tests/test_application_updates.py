import asyncio
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, AsyncMock, Mock
import uuid
import zipfile

from backend.application_updates import (ApplicationUpdates, API, ReleaseRedirects,
    release_url, select_release, parse_checksum, unpack_package, sha256)
from backend.update_helper import validate_job, replace, update_receipt, health_matches, wait_processes
from backend.settings import atomic_json
from urllib.request import Request


def release(v='0.4.120'):
    name='PhotoshopMenu-Backend-'+v+'.zip';tag='v'+v
    return {'id':41,'tag_name':tag,'draft':False,'prerelease':False,'body':'Changes',
            'assets':[{'id':n,'name':f,'state':'uploaded','size':size,
                       'browser_download_url':release_url(tag,f),'digest':None}
                      for n,f,size in ((1,name,100),(2,name+'.sha256',100))]}


class UpdateValidationTests(unittest.TestCase):
    def test_only_higher_stable_release_and_exact_repo_assets(self):
        self.assertTrue(select_release(release(),'0.4.119')['available'])
        for current in ('0.4.120','0.4.121','0.5.0'):
            self.assertFalse(select_release(release(),current)['available'])
        for field,value in (('draft',True),('prerelease',True),('tag_name','v0.4.120-rc'),('id',True)):
            item=release();item[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):select_release(item,'0.4.119')
        for field,value in (('browser_download_url','https://github.com/evil/repo/payload.exe'),('size',2**40),('digest','md5:abc'),('state','new'),('id',False)):
            item=release();item['assets'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):select_release(item,'0.4.119')
        item=release();item['assets'].append(item['assets'][0])
        with self.assertRaises(ValueError):select_release(item,'0.4.119')

    def test_checksum_binds_filename_and_redirects_require_trusted_https(self):
        text=b'a'*64+b'  package.zip\n'
        self.assertEqual(parse_checksum(text,'package.zip'),'a'*64)
        with self.assertRaises(ValueError):parse_checksum(text,'other.zip')
        handler=ReleaseRedirects();request=Request(API)
        for url in ('http://github.com/test','https://evil.com/test','https://github.com:444/test','https://user@github.com/test'):
            with self.subTest(url=url),self.assertRaises(ValueError):handler.redirect_request(request,None,302,'',{},url)
        self.assertEqual(handler.redirect_request(request,None,302,'',{},'https://release-assets.githubusercontent.com/test').full_url,
                         'https://release-assets.githubusercontent.com/test')

    def package(self, folder, additional=None, checksum=None):
        exe=b'MZ example exe';path=folder/'package.zip'
        with zipfile.ZipFile(path,'w') as bundle:
            bundle.writestr('PhotoshopMenu.exe',exe)
            bundle.writestr('PhotoshopMenu.exe.sha256',(checksum or hashlib.sha256(exe).hexdigest())+'  PhotoshopMenu.exe\n')
            bundle.writestr('PhotoshopMenu-UXP-0.4.120.zip',b'plugin')
            if additional:
                entry=zipfile.ZipInfo('placeholder');entry.filename=additional
                bundle.writestr(entry,b'bad')
        return path

    def test_zip_never_extracts_untrusted_paths_and_rejects_bad_hash_version(self):
        for unsafe in ('../other.exe','/other.exe','C:/other.exe','folder\\other.exe'):
            with tempfile.TemporaryDirectory() as directory:
                folder=Path(directory);package=self.package(folder,unsafe)
                with self.subTest(path=unsafe),self.assertRaises(ValueError):unpack_package(package,folder,'0.4.120',sha256(package))
                self.assertFalse((folder/'PhotoshopMenu.exe').exists())
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);package=self.package(folder)
            with self.assertRaises(ValueError):unpack_package(package,folder,'0.4.120','0'*64)
            with patch('backend.application_updates.executable_version',return_value='0.4.119'),self.assertRaises(ValueError):
                unpack_package(package,folder,'0.4.120',sha256(package))
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);package=self.package(folder,checksum='0'*64)
            with self.assertRaises(ValueError):unpack_package(package,folder,'0.4.120',sha256(package))
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);package=self.package(folder)
            with patch('backend.application_updates.executable_version',return_value='0.4.120'):
                result=unpack_package(package,folder,'0.4.120',sha256(package))
                self.assertEqual(result['sha256'],sha256(folder/'PhotoshopMenu.exe'))

    def test_apply_identity_downgrade_tamper_and_other_service_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime=Path(directory);folder=runtime/'application-updates'/uuid.uuid4().hex;folder.mkdir(parents=True)
            target=runtime/'app/PhotoshopMenu.exe';target.parent.mkdir();target.write_bytes(b'old')
            helper=folder/'update-host.exe';helper.write_bytes(b'new')
            source=folder/'PhotoshopMenu.exe';source.write_bytes(b'new')
            job={'schema':1,'id':folder.name,'runtime':str(runtime),'target':str(target),'old_version':'0.4.119',
                 'new_version':'0.4.120','old_sha256':sha256(target),'new_sha256':sha256(source),
                 'pids':[123],'port':15151,'headless':True,'no_desktop':True}
            path=folder/'job.json';atomic_json(path,job)
            def metadata(path):return '0.4.120' if Path(path)==source else '0.4.119'
            with patch('backend.update_helper.executable_version',side_effect=metadata):
                self.assertEqual(validate_job(path,helper)[2],target)
                source.write_bytes(b'changed')
                with self.assertRaises(ValueError):validate_job(path,helper)
                source.write_bytes(b'new');job['new_version']='0.4.119';atomic_json(path,job)
                with self.assertRaises(ValueError):validate_job(path,helper)
            health={'app':'photoshop-menu','version':'0.4.120','executable':str(target),'pid':123}
            self.assertTrue(health_matches(health,target,'0.4.120'))
            health['executable']=str(runtime/'other.exe');self.assertFalse(health_matches(health,target,'0.4.120'))

    def test_replace_preserves_unrelated_files_and_receipt_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime=Path(directory);old=runtime/'PhotoshopMenu.exe';new=runtime/'candidate.exe'
            old.write_bytes(b'old');new.write_bytes(b'new');settings=runtime/'settings.json';settings.write_text('user settings')
            receipt=runtime/'offline-install.json';atomic_json(receipt,{'owned':{str(old):sha256(old)},'version':'0.4.119'})
            original=sha256(old);replace(new,old)
            update_receipt(runtime,old,original,sha256(new),'0.4.120')
            self.assertEqual(old.read_bytes(),b'new');self.assertEqual(settings.read_text(),'user settings')
            self.assertEqual(json.loads(receipt.read_text())['owned'][str(old)],sha256(new))
            saved=receipt.read_bytes();update_receipt(runtime,old,'0'*64,'1'*64,'0.4.121');self.assertEqual(receipt.read_bytes(),saved)

    def test_update_wait_timeout_never_kills_or_replaces(self):
        kernel=SimpleNamespace(WaitForSingleObject=Mock(return_value=258))
        with self.assertRaises(TimeoutError):wait_processes(kernel,[1],seconds=0)
        self.assertFalse(kernel.WaitForSingleObject.called)

    def test_failed_new_start_restores_actual_old_bytes_receipt_and_config(self):
        from backend.update_helper import apply
        with tempfile.TemporaryDirectory() as directory:
            runtime=Path(directory);folder=runtime/'application-updates'/uuid.uuid4().hex;folder.mkdir(parents=True)
            target=runtime/'PhotoshopMenu.exe';target.write_bytes(b'old exe')
            source=folder/'PhotoshopMenu.exe';source.write_bytes(b'new exe')
            (runtime/'settings.json').write_bytes(b'keep user settings')
            atomic_json(runtime/'offline-install.json',{'owned':{str(target):sha256(target)},'version':'0.4.119'})
            saved=(runtime/'offline-install.json').read_bytes()
            job={'id':folder.name,'runtime':str(runtime),'old_sha256':sha256(target),'new_sha256':sha256(source),
                 'old_version':'0.4.119','new_version':'0.4.120','pids':[123],'port':15163,'headless':True,'no_desktop':True}
            process=SimpleNamespace(poll=lambda:1)
            with patch('backend.update_helper.validate_job',return_value=(job,folder,target,source)),\
                 patch('backend.update_helper.open_processes',return_value=(SimpleNamespace(),[])),\
                 patch('backend.update_helper.wait_processes'),\
                 patch('backend.update_helper.executable_version',return_value='0.4.120'),\
                 patch('backend.update_helper.launch',return_value=process) as launch_mock,\
                 patch('backend.update_helper.build_opener',return_value=SimpleNamespace(open=Mock(side_effect=OSError('startup failed')))):
                apply(folder/'job.json')
            self.assertEqual(target.read_bytes(),b'old exe')
            self.assertEqual((runtime/'offline-install.json').read_bytes(),saved)
            self.assertEqual((runtime/'settings.json').read_bytes(),b'keep user settings')
            self.assertEqual(json.loads((folder/'result.json').read_text('utf-8'))['phase'],'rolled-back')
            self.assertEqual(launch_mock.call_count,2)

    def test_interrupted_download_does_not_clear_previously_verified_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            updater=ApplicationUpdates(directory,'0.4.119')
            folder=updater.root/uuid.uuid4().hex;folder.mkdir(parents=True)
            updater.change(phase='downloading',staged={'folder':str(folder),'sha256':'a'*64,'version':'0.4.120'})
            restarted=ApplicationUpdates(directory,'0.4.119')
            self.assertEqual(restarted.snapshot()['phase'],'error')
            self.assertEqual(restarted.snapshot()['staged']['version'],'0.4.120')
            self.assertNotIn('staged',ApplicationUpdates(directory,'0.4.120').snapshot())


class UpdateAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_network_truncation_or_digest_mismatch_never_prepares_install(self):
        with tempfile.TemporaryDirectory() as directory:
            updater=ApplicationUpdates(directory,'0.4.119')
            item={'url':release_url('v0.4.120','package.zip'),'size':5,'digest':None}
            for payload,digest in ((b'ab',None),(b'abcdef',None),(b'abcde','sha256:'+'0'*64)):
                with self.subTest(payload=payload,digest=digest):
                    item['digest']=digest
                    stream=io.BytesIO(payload)
                    with patch('backend.application_updates.opener',return_value=SimpleNamespace(open=lambda *a,**k:stream)):
                        with self.assertRaises(ValueError):updater.fetch(item)
            self.assertNotIn('staged',updater.snapshot())

    async def test_conditionally_cached_release_is_revalidated_against_running_version(self):
        from urllib.error import HTTPError
        with tempfile.TemporaryDirectory() as directory:
            updater=ApplicationUpdates(directory,'0.4.120')
            updater.change(release=select_release(release(),'0.4.119'),etag='cached')
            client=SimpleNamespace(open=Mock(side_effect=HTTPError(API,304,'Not modified',{},None)))
            with patch('backend.application_updates.opener',return_value=client):updater.check()
            self.assertEqual(updater.snapshot()['phase'],'current');self.assertFalse(updater.snapshot()['available'])
            self.assertEqual(client.open.call_args.args[0].get_header('If-none-match'),'cached')

    async def test_download_job_returns_immediately_and_preserves_error_without_install(self):
        with tempfile.TemporaryDirectory() as directory:
            updater=ApplicationUpdates(directory,'0.4.119')
            with patch.object(updater,'download',side_effect=ValueError('bad checksum')):
                updater.start('download');self.assertEqual(updater.snapshot()['phase'],'downloading')
                with self.assertRaises(RuntimeError):updater.start('check')
                await updater.worker
            self.assertEqual(updater.snapshot()['phase'],'error');self.assertIn('bad checksum',updater.snapshot()['error'])
            self.assertNotIn('job',updater.snapshot());await updater.close()

    async def test_install_is_refused_for_busy_pending_menu_or_startup_without_invoking_helper(self):
        from backend.main import Application
        with tempfile.TemporaryDirectory() as directory:
            bridge=SimpleNamespace(busy=False,replace_scripts=Mock(),transport=SimpleNamespace(pending=SimpleNamespace(value=None,error=None)))
            app=Application(15163,bridge=bridge,runtime=directory)
            app.application_updates.prepare_install=AsyncMock()
            for setting,value in (('busy',True),('pending','unconfirmed'),('menu',True),('lock',True)):
                bridge.busy=setting=='busy';bridge.transport.pending.value=value if setting=='pending' else None
                app.desktop=SimpleNamespace(visible=setting=='menu')
                if setting=='lock':await app.operation_lock.acquire()
                with self.subTest(setting=setting),self.assertRaises(RuntimeError):await app.dispatch('application.update.install',{})
                if setting=='lock':app.operation_lock.release()
            app.application_updates.prepare_install.assert_not_called()
            self.assertFalse(app.updating);self.assertFalse(app.stop_event.is_set())
