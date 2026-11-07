import http.client
import json
import math
import os
import shutil
import struct
import tempfile
import threading
import time
import unittest
import wave
import io
from pathlib import Path
from unittest.mock import patch

from mimic.library import Library, suggest, select_fragment
from mimic.server import App, Handler, ThreadingHTTPServer
from mimic.sources import LicensedCatalog


def tone(path):
    with wave.open(str(path),'wb') as f:
        f.setparams((1,2,48000,0,'NONE','not compressed'))
        data=[0 if n<12000 or n>84000 else int(9000*math.sin(2*math.pi*440*n/48000)) for n in range(96000)]
        f.writeframes(struct.pack('<'+'h'*len(data),*data))


class FakeAudio:
    def __init__(self): self.calls=[]
    def command(self,op,**data):
        self.calls.append((op,data))
        if op=='devices': return {'devices':[]}
        return {'playing':None,'volume':.65,'mic':False,'output':0,'outputName':'test','running':False}


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.audio=FakeAudio()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.port=self.server.server_port
        self.app=App(self.tmp.name,self.audio,'127.0.0.1',self.port)
        self.server.app=self.app
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.admin=self.app.issue('admin','test');self.remote=self.app.issue('remote','phone')
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def req(self,path,data=None,token=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        h={'Content-Type':'application/json'}
        if token:h['Cookie']='mimic='+token
        h.update(headers or {})
        conn.request('GET' if data is None else 'POST',path,None if data is None else json.dumps(data),h)
        res=conn.getresponse();raw=res.read();status=res.status;cookie=res.getheader('Set-Cookie');conn.close()
        try:body=json.loads(raw)
        except ValueError:body=raw
        return status,body,cookie
    def test_public_static_and_health(self):
        self.assertEqual(self.req('/')[0],200)
        self.assertEqual(self.req('/api/health')[1]['version'],'0.4.3-unified')
    def test_remote_home_screen_has_public_vupio_icons(self):
        status,manifest,_=self.req('/manifest.webmanifest')
        self.assertEqual(status,200)
        self.assertEqual(manifest['short_name'],'VUPIO')
        for path,size in [('/apple-touch-icon.png',180),*[(i['src'],int(i['sizes'].split('x')[0])) for i in manifest['icons']]]:
            with self.subTest(path=path):
                status,image,_=self.req(path)
                self.assertEqual(status,200)
                self.assertEqual(image[:8],b'\x89PNG\r\n\x1a\n')
                self.assertEqual(struct.unpack('>II',image[16:24]),(size,size))
    def test_no_anonymous_controls(self):
        for path in ['/api/play','/api/stop','/api/panic','/api/upload','/api/output']:
            self.assertEqual(self.req(path,{},None)[0],403)
        self.assertEqual(self.req('/api/state')[0],403)
    def test_login_local_with_secret(self):
        self.assertEqual(self.req('/api/login',{'key':'wrong'})[0],403)
        s,_,c=self.req('/api/login',{'key':self.app.admin_key})
        self.assertEqual(s,200);self.assertIn('HttpOnly',c);self.assertIn('SameSite=Strict',c)
    def test_remote_role_restrictions(self):
        for path in ['/api/output','/api/mic','/api/delete','/api/edit','/api/prepare','/api/pair/new','/api/revoke','/api/upload','/api/mixer','/api/audio/test','/api/audio/probe','/api/audio/mic-test','/api/audio/mic-test-stop','/api/audio/restart','/api/ai/web-settings']:
            self.assertEqual(self.req(path,{},self.remote)[0],403,path)
        self.assertEqual(self.req('/api/settings',token=self.remote)[0],403)
        self.assertEqual(self.req('/api/audio',token=self.remote)[0],403)
    def test_mixer_validation_and_preferences(self):
        self.assertEqual(self.req('/api/mixer',{'gain':float('nan')},self.admin)[0],400)
        self.assertEqual(self.req('/api/mixer',{'gain':2},self.admin)[0],400)
        self.assertEqual(self.req('/api/mixer',{'polyphony':'false'},self.admin)[0],400)
        self.assertEqual(self.req('/api/mixer',{'gain':.35,'polyphony':True},self.admin)[0],200)
        preferences=json.loads(self.app.preferences_path.read_text())
        self.assertEqual(preferences['micGain'],.35);self.assertTrue(preferences['polyphony'])
        self.assertNotIn('monitor',preferences)
    def test_diagnostic_is_a_real_wave_file(self):
        self.assertEqual(self.req('/api/audio/test',{},self.admin)[0],200)
        with wave.open(str(self.app.library.root/'mimic-diagnostic.wav')) as wav:
            self.assertEqual(wav.getnchannels(),2);self.assertEqual(wav.getframerate(),48000);self.assertEqual(wav.getnframes(),48000)
    def test_local_listening_choice_persists_by_uid(self):
        with patch.object(self.audio,'command',return_value={'monitorUID':'headphones-stable-uid'}):
            self.assertEqual(self.req('/api/mixer',{'monitor':True,'monitorDevice':117},self.admin)[0],200)
        preferences=json.loads(self.app.preferences_path.read_text())
        self.assertTrue(preferences['monitor'])
        self.assertEqual(preferences['monitorUID'],'headphones-stable-uid')
        self.assertNotIn('monitorDevice',preferences)
        replacement=FakeAudio()
        App(self.tmp.name,replacement,'127.0.0.1',self.port)
        self.assertIn(('mixer',{'monitor':True,'monitorUID':'headphones-stable-uid','start':False}),replacement.calls)
        self.assertNotIn('mic',[op for op,_ in replacement.calls])

    def test_local_listening_defaults_on_without_opening_hardware(self):
        self.assertIn(('mixer',{'monitor':True,'monitorUID':'','start':False}),self.audio.calls)
        self.assertNotIn('play',[op for op,_ in self.audio.calls])

    def test_local_listening_explicit_off_survives_restart(self):
        self.assertEqual(self.req('/api/mixer',{'monitor':False},self.admin)[0],200)
        replacement=FakeAudio()
        App(self.tmp.name,replacement,'127.0.0.1',self.port)
        self.assertIn(('mixer',{'monitor':False,'monitorUID':'','start':False}),replacement.calls)

    def test_physical_diagnostic_never_generates_tone(self):
        self.audio.calls.clear()
        self.assertEqual(self.req('/api/audio/mic-test',{'device':112,'gain':.5},self.admin)[0],200)
        self.assertEqual(self.audio.calls,[('mic_test',{'device':112,'gain':.5})])
        self.assertFalse((self.app.library.root/'mimic-diagnostic.wav').exists())
        self.assertEqual(self.req('/api/audio/mic-test-stop',{},self.admin)[0],200)
        self.assertEqual(self.audio.calls[-1][0],'mic_test_stop')
    def test_physical_gain_and_switch_validation(self):
        for gain in [-1,2,float('nan')]:
            self.assertEqual(self.req('/api/audio/mic-test',{'gain':gain},self.admin)[0],400)
        self.assertEqual(self.req('/api/mic',{'enabled':'false'},self.admin)[0],400)
    def test_stale_virtual_input_preference_cannot_break_startup(self):
        self.app.save_preference(inputUID='MIMICAudioDevice_UID')
        class Devices(FakeAudio):
            def command(self,op,**data):
                if op=='devices':return {'devices':[],'inputs':[{'id':90,'uid':'MIMICAudioDevice_UID'}],'physicalInputs':[]}
                if op=='input':raise AssertionError('Virtual input selected as physical')
                return super().command(op,**data)
        App(self.tmp.name,Devices(),'127.0.0.1',self.port)
    def test_phone_controls_and_panic(self):
        self.assertEqual(self.req('/api/stop',{},self.remote)[0],200)
        self.assertEqual(self.req('/api/panic',{},self.remote)[0],200)
        self.assertEqual(self.audio.calls[-1][0],'panic')
        self.assertEqual(self.req('/api/volume',{'value':.2},self.remote)[0],200)
        self.assertEqual(self.req('/api/volume',{'value':8},self.remote)[0],400)
    def test_volume_persists_without_enabling_microphone(self):
        self.req('/api/volume',{'value':.42},self.remote)
        replacement=FakeAudio()
        App(self.tmp.name,replacement,'127.0.0.1',self.port)
        self.assertIn(('volume',{'value':.42}),replacement.calls)
        self.assertNotIn('mic',[op for op,_ in replacement.calls])
    def test_preview_volume_survives_a_stopped_audio_helper(self):
        with patch.object(self.audio, 'command', side_effect=ValueError('\u0410\u0443\u0434\u0438\u043e\u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u043e \u043d\u0435 \u043e\u0442\u0432\u0435\u0447\u0430\u0435\u0442')):
            status, result, _ = self.req('/api/volume', {'value': .24}, self.admin)
            self.assertEqual(status, 200)
            self.assertEqual(result['volume'], .24)
            self.assertEqual(self.req('/api/state', token=self.admin)[1]['audio']['volume'], .24)
        replacement = FakeAudio()
        App(self.tmp.name, replacement, '127.0.0.1', self.port)
        self.assertIn(('volume', {'value': .24}), replacement.calls)

    def test_pair_code_one_use_and_expiry(self):
        _,result,_=self.req('/api/pair/new',{},self.admin)
        code=result['code'];self.assertEqual(len(code),8)
        status,_,cookie=self.req('/api/pair',{'code':code})
        self.assertEqual(status,200);self.assertIsNotNone(cookie)
        self.assertEqual(self.req('/api/pair',{'code':code})[0],403)
        self.app.pair_code='12345678';self.app.pair_until=time.time()-1
        self.assertEqual(self.req('/api/pair',{'code':'12345678'})[0],403)
    def test_pair_rate_limit(self):
        for _ in range(5):self.req('/api/pair',{'code':'wrong'})
        self.assertEqual(self.req('/api/pair',{'code':'wrong'})[0],429)
    def test_csrf_and_host(self):
        self.assertEqual(self.req('/api/stop',{},self.admin,{'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.req('/api/state',token=self.admin,headers={'Host':'evil.example'})[0],403)
        self.assertEqual(self.req('/api/stop',{},self.admin,{'Sec-Fetch-Site':'cross-site'})[0],403)
    def test_revoke(self):
        self.assertEqual(self.req('/api/revoke',{},self.admin)[0],200)
        self.assertEqual(self.req('/api/state',token=self.remote)[0],403)
        self.assertEqual(self.req('/api/state',token=self.admin)[0],200)
    def test_qr_has_no_pair_secret(self):
        self.req('/api/pair/new',{},self.admin)
        status,raw,_=self.req('/api/qr',token=self.admin)
        self.assertEqual(status,200);self.assertIn(b'<svg',raw)
    def test_path_traversal_and_missing_file(self):
        self.assertEqual(self.req('/../../etc/passwd')[0],403)
        self.assertEqual(self.req('/api/file/not-found',token=self.admin)[0],400)
        self.assertEqual(self.req('/api/file/not-found',token=self.remote)[0],403)
    def test_remote_inventory_and_individual_revoke(self):
        keep=self.app.issue('remote','second phone')
        self.assertEqual(self.req('/api/remotes',token=self.remote)[0],403)
        status,rows,_=self.req('/api/remotes',token=self.admin)
        self.assertEqual(status,200)
        phone=next(r for r in rows if r['name']=='phone')
        self.assertNotIn(self.remote,json.dumps(rows))
        self.assertEqual(self.req('/api/remotes/revoke',{'id':phone['id']},self.admin)[0],200)
        self.assertEqual(self.req('/api/state',token=self.remote)[0],403)
        self.assertEqual(self.req('/api/state',token=keep)[0],200)
    def test_audio_preview_range_and_wave_permissions(self):
        path=Path(self.tmp.name)/'source.wav';tone(path)
        item=self.app.library.import_file(path,'Test waveform')
        url='/api/file/'+item['id']
        status,body,_=self.req(url,token=self.admin,headers={'Range':'bytes=0-11'})
        self.assertEqual(status,206);self.assertEqual(body[:4],b'RIFF');self.assertEqual(len(body),12)
        self.assertEqual(self.req(url,token=self.admin,headers={'Range':'bytes=99999999-'})[0],416)
        self.assertEqual(self.req(url,token=self.remote,headers={'Range':'bytes=0-11'})[0],403)
        wave_url='/api/ai/wave/clip/'+item['id']
        self.assertEqual(self.req(wave_url,token=self.remote)[0],403)
        status,body,_=self.req(wave_url,token=self.admin)
        self.assertEqual(status,200);self.assertAlmostEqual(body['duration'],2)
        self.assertEqual(body['peaks'][0],[0,0]);self.assertGreater(body['peaks'][240][1],.1)
        self.app._studio.close()
    def test_virtual_route_is_selected_without_starting_it(self):
        class Devices(FakeAudio):
            def command(self,op,**data):
                if op=='devices':return {'devices':[{'id':42,'uid':'MIMICAudioDevice_UID'}],'physicalInputs':[]}
                return super().command(op,**data)
        audio=Devices();App(self.tmp.name,audio,'127.0.0.1',self.port)
        self.assertIn(('output',{'device':42,'start':False}),audio.calls)
        self.assertNotIn('mic',[op for op,_ in audio.calls])
    def test_library_still_loads_after_audio_disconnect(self):
        with patch.object(self.audio,'command',side_effect=ValueError('\u0410\u0443\u0434\u0438\u043e\u0434\u0432\u0438\u0436\u043e\u043a \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d')):
            status,body,_=self.req('/api/state',token=self.admin)
            self.assertEqual(status,200);self.assertEqual(body['items'],[])
            self.assertFalse(body['audio']['running']);self.assertIn('\u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d',body['audio']['error'])
    def test_semantic_explicitly_needs_model(self):
        with patch.dict(os.environ,{},clear=True):
            status,body,_=self.req('/api/search',{'query':'\u0433\u043e\u0440\u0430','semantic':True},self.remote)
        self.assertEqual(status,400);self.assertIn('MIMIC_EMBED_MODEL',body['error'])


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg not installed')
class AudioFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.lib=Library(self.root/'library');self.source=self.root/'tone.wav';tone(self.source)
        self.item=self.lib.import_file(self.source,'\u0422\u0435\u0441\u0442\u043e\u0432\u0430\u044f \u0433\u043e\u0440\u0430','\u042d\u0444\u0444\u0435\u043a\u0442\u044b','\u0430\u0443\u0440\u0430, \u044d\u043f\u0438\u0447\u043d\u043e','\u0412\u0438\u0434 \u0441 \u0432\u0435\u0440\u0448\u0438\u043d\u044b')
    def tearDown(self):self.tmp.cleanup()
    def test_import_format_persistence_and_search(self):
        self.assertAlmostEqual(self.item['duration'],2,places=2)
        with wave.open(str(self.lib.path(self.item['id']))) as f:
            self.assertEqual((f.getnchannels(),f.getframerate()),(2,48000))
        self.assertEqual(Library(self.lib.root).items()[0]['title'],'\u0422\u0435\u0441\u0442\u043e\u0432\u0430\u044f \u0433\u043e\u0440\u0430')
        self.assertEqual(self.lib.search('\u0430\u0443\u0440\u0430')['items'][0]['id'],self.item['id'])
    def test_trim_original_preserved(self):
        result=self.lib.prepare({'id':self.item['id'],'start':.3,'end':1.4,'normalize':True})
        self.assertNotEqual(result['id'],self.item['id']);self.assertEqual(len(self.lib.items()),2)
        self.assertAlmostEqual(result['duration'],1.1,delta=.05)
    def test_silence_removed(self):
        result=self.lib.prepare({'id':self.item['id'],'start':0,'end':2,'silence':True})
        self.assertLess(result['duration'],1.85);self.assertGreater(result['duration'],1.3)
    def test_invalid_trim(self):
        for start,end in [(-1,1),(1,0),(0,99),(float('nan'),2)]:
            with self.assertRaises(ValueError):self.lib.prepare({'id':self.item['id'],'start':start,'end':end})
    def test_edit_favorite_delete(self):
        id=self.item['id'];self.lib.edit(id,{'favorite':True,'title':'\u041d\u043e\u0432\u043e\u0435'})
        self.assertEqual(self.lib.get(id)['favorite'],1)
        path=self.lib.path(id);self.lib.delete(id)
        self.assertFalse(path.exists());self.assertTrue(self.source.exists())
    def test_invalid_upload_leaves_no_orphan(self):
        invalid=self.root/'bad.txt';invalid.write_text('not audio')
        with self.assertRaises(ValueError):self.lib.import_file(invalid,'Bad')
        self.assertEqual(len(list(self.lib.files.iterdir())),1)
    def test_embedding_api_ranking_and_cache(self):
        other=self.lib.import_file(self.source,'\u0421\u043c\u0435\u0448\u043d\u043e\u0439 \u043f\u0440\u043e\u0432\u0430\u043b','\u041c\u0435\u043c\u044b')
        calls=[]
        def fake_open(request,timeout):
            text=json.loads(request.data)['input'];calls.append(text)
            vector=[1,0] if ('\u0432\u0435\u0440\u0448\u0438\u043d\u044b' in text or text=='\u043a\u0440\u0430\u0441\u0438\u0432\u044b\u0439 \u043f\u0435\u0439\u0437\u0430\u0436') else [0,1]
            return io.BytesIO(json.dumps({'embeddings':[vector]}).encode())
        with patch.dict(os.environ,{'MIMIC_EMBED_MODEL':'test-local'}), patch('mimic.library.urlopen',side_effect=fake_open):
            result=self.lib.search('\u043a\u0440\u0430\u0441\u0438\u0432\u044b\u0439 \u043f\u0435\u0439\u0437\u0430\u0436',True)
            self.assertEqual(result['items'][0]['id'],self.item['id'])
            self.lib.search('\u043a\u0440\u0430\u0441\u0438\u0432\u044b\u0439 \u043f\u0435\u0439\u0437\u0430\u0436',True)
        self.assertEqual(len(calls),3)


class StudioTests(unittest.TestCase):
    def test_fragment(self):
        r=select_fragment('\u044d\u0442\u0430 \u0430\u0443\u0440\u0430',[{'start':1,'end':3,'text':'\u043d\u0443 \u0432\u043e\u0442 \u044d\u0442\u0430 \u0430\u0443\u0440\u0430'}])
        self.assertEqual((r['start'],r['end']),(1,3))
        with self.assertRaises(ValueError):select_fragment('\u043d\u0435\u0442',[])
    def test_suggest(self):
        self.assertEqual(suggest('\u042d\u043f\u0438\u0447\u043d\u0430\u044f \u0433\u043e\u0440\u0430')['tags'],'\u044d\u043f\u0438\u0447\u043d\u0430\u044f, \u0433\u043e\u0440\u0430')
    def test_catalog_license_and_https(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'sources.json'
            path.write_text(json.dumps([{'title':'\u0433\u043e\u0440\u0430','page_url':'https://example.com','license':'CC0'},
                                        {'title':'\u0433\u043e\u0440\u0430','page_url':'javascript:alert(1)','license':'CC0'},
                                        {'title':'\u0433\u043e\u0440\u0430','page_url':'https://example.com'}]))
            self.assertEqual(len(LicensedCatalog(path).search('\u0433\u043e\u0440\u0430')),1)


if __name__=='__main__':unittest.main()
