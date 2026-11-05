import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from mimic.catalog import Commons,reusable
from mimic.editor import make_plan,parse_rule,phrase_span
from mimic.jobs import Jobs
from mimic.library import Library
from mimic.studio import Studio
from test_mimic import tone


class EditorTests(unittest.TestCase):
    def test_russian_and_english_operations(self):
        for text in ['\u041e\u0431\u0440\u0435\u0436\u044c \u043f\u0435\u0440\u0432\u044b\u0435 \u043f\u044f\u0442\u044c \u0441\u0435\u043a\u0443\u043d\u0434','remove first five seconds']:
            plan=make_plan(parse_rule(text),20)
            self.assertEqual(plan['start'],5)
        plan=make_plan(parse_rule('\u0423\u0431\u0435\u0440\u0438 \u0442\u0438\u0448\u0438\u043d\u0443, \u0441\u0434\u0435\u043b\u0430\u0439 \u0433\u0440\u043e\u043c\u043a\u043e\u0441\u0442\u044c \u0440\u043e\u0432\u043d\u0435\u0435 \u0438 \u043f\u043b\u0430\u0432\u043d\u043e\u0435 \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u0435'),20)
        self.assertTrue(plan['silence']);self.assertTrue(plan['normalize']);self.assertEqual(plan['fade_out'],.5)
    def test_phrase_timing_and_tail(self):
        segments=[{'start':1,'end':2,'text':'\u041d\u0443'},{'start':2,'end':3,'text':'\u0432\u043e\u0442'},{'start':3,'end':4,'text':'\u044d\u0442\u0430 \u0430\u0443\u0440\u0430'},{'start':5,'end':6,'text':'\u043f\u043e\u0433\u043d\u0430\u043b\u0438'}]
        plan=make_plan(parse_rule('\u041e\u0441\u0442\u0430\u0432\u044c \u0442\u0440\u0438 \u0441\u0435\u043a\u0443\u043d\u0434\u044b \u043f\u043e\u0441\u043b\u0435 \u043d\u0443\u0436\u043d\u043e\u0439 \u0440\u0435\u043f\u043b\u0438\u043a\u0438','\u044d\u0442\u0430 \u0430\u0443\u0440\u0430'),10,segments)
        self.assertEqual((plan['start'],plan['end']),(4,7))
        keep=make_plan(parse_rule('\u041e\u0441\u0442\u0430\u0432\u044c \u0444\u0440\u0430\u0437\u0443 \u0438 \u0442\u0440\u0438 \u0441\u0435\u043a\u0443\u043d\u0434\u044b \u043f\u043e\u0441\u043b\u0435','\u044d\u0442\u0430 \u0430\u0443\u0440\u0430'),10,segments)
        self.assertEqual((keep['start'],keep['end']),(3,7))
    def test_no_invented_phrase(self):
        with self.assertRaises(ValueError):phrase_span('\u043d\u0435\u0441\u0443\u0449\u0435\u0441\u0442\u0432\u0443\u044e\u0449\u0430\u044f \u0440\u0435\u043f\u043b\u0438\u043a\u0430',[{'start':0,'end':1,'text':'\u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430'}])
    def test_unknown_command_and_invalid_time(self):
        self.assertIsNone(parse_rule('\u0441\u0434\u0435\u043b\u0430\u0439 \u043d\u0435\u043e\u0431\u044b\u0447\u043d\u043e\u0435'))
        with self.assertRaises(ValueError):make_plan({'operation':'trim','start':float('nan'),'end':2},3)
        with self.assertRaises(ValueError):make_plan({'operation':'remove_first','seconds':99},3)
    def test_drop_is_only_energy_candidate(self):
        plan=make_plan(parse_rule('\u041d\u0430\u0439\u0434\u0438 \u043c\u043e\u043c\u0435\u043d\u0442 \u043f\u0435\u0440\u0435\u0434 \u0434\u0440\u043e\u043f\u043e\u043c'),10,features={'onsets':[{'time':6,'strength':.2}]})
        self.assertEqual((plan['start'],plan['end']),(3,6));self.assertIn('warning',plan)
        with self.assertRaises(ValueError):make_plan(parse_rule('\u043f\u0435\u0440\u0435\u0434 \u0434\u0440\u043e\u043f\u043e\u043c'),10,features={'onsets':[]})


class CatalogTests(unittest.TestCase):
    def page(self,license='CC BY 4.0',url='https://upload.wikimedia.org/a.wav',mime='audio/wav'):
        return {'pageid':123,'title':'File:Real.wav','imageinfo':[{'url':url,'descriptionurl':'https://commons.wikimedia.org/wiki/File:Real.wav','size':100,'mime':mime,'extmetadata':{'LicenseShortName':{'value':license},'Artist':{'value':'<b>Author</b>'},'ImageDescription':{'value':'A real recording'}}}]}
    def test_license_and_attribution(self):
        item=Commons().parse(self.page());self.assertTrue(item['can_import']);self.assertEqual(item['author'],'Author')
        for license in ['All rights reserved','CC BY-NC 4.0','CC BY-ND 4.0','']:
            self.assertFalse(Commons().parse(self.page(license))['can_import'])
    def test_no_untrusted_host_or_non_audio(self):
        self.assertIsNone(Commons().parse(self.page(url='http://127.0.0.1/internal')))
        self.assertIsNone(Commons().parse(self.page(mime='text/html')))
        with self.assertRaises(ValueError):Commons().resolve('https://evil.example/file')
    def test_actual_api_query_not_a_static_catalog(self):
        with patch('mimic.catalog.get_json',return_value={'query':{'pages':[self.page()]}}) as get:
            result=Commons().search('thunder')
        self.assertEqual(len(result),1);self.assertIn('generator=search',get.call_args.args[0]);self.assertIn('thunder',get.call_args.args[0])
    def test_import_rechecks_license(self):
        with patch.object(Commons,'query',return_value={'query':{'pages':[self.page('All rights reserved')]}}):
            with self.assertRaises(ValueError):Commons().resolve('commons:123')
    def test_midi_and_oversized_are_not_advertised_as_importable(self):
        self.assertFalse(Commons().parse(self.page(url='https://upload.wikimedia.org/test.mid',mime='audio/midi'))['can_import'])
        large=self.page();large['imageinfo'][0]['size']=101*1024*1024
        self.assertFalse(Commons().parse(large)['can_import'])
        long=self.page();long['imageinfo'][0]['duration']=1201
        self.assertFalse(Commons().parse(long)['can_import'])


class JobTests(unittest.TestCase):
    def test_large_results_are_fetched_once_not_in_status_poll(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs=Jobs(Library(tmp));id=jobs.submit('large',lambda j:{'text':'a'*200000})['job_id']
            until=time.monotonic()+2
            while time.monotonic()<until and jobs.get(id)['status']!='done':time.sleep(.02)
            self.assertEqual(jobs.snapshot(include_results=False)[0]['result'],{})
            self.assertEqual(len(jobs.get(id)['result']['text']),200000);jobs.close()
    def test_cancel_and_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib=Library(tmp);jobs=Jobs(lib);gate=threading.Event()
            def work(job):
                gate.set()
                while True:job.check();time.sleep(.01)
            id=jobs.submit('slow',work)['job_id'];self.assertTrue(gate.wait(1));jobs.cancel(id)
            until=time.monotonic()+3
            while time.monotonic()<until and jobs.snapshot()[0]['status'] not in ['cancelled','failed']:time.sleep(.02)
            self.assertEqual(jobs.snapshot()[0]['status'],'cancelled');jobs.close()
            other=Jobs(lib);self.assertEqual(other.snapshot()[0]['status'],'cancelled');other.close()


class StudioFilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.library=Library(self.root/'library');source=self.root/'tone.wav';tone(source)
        self.item=self.library.import_file(source,'\u041e\u0440\u0438\u0433\u0438\u043d\u0430\u043b','Effect')
        self.studio=Studio(self.library,'/usr/bin/true')
        class Job:
            def check(self):pass
            def update(self,*_):pass
        self.job=Job()
    def tearDown(self):self.studio.close();self.tmp.cleanup()
    def test_render_commit_idempotent_and_undo_preserves_original(self):
        draft=self.studio.render({'id':self.item['id'],'start':.2,'end':1.5,'normalize':True,'fade_out':.2},self.job)
        _,path=self.studio.draft(draft['draft_id']);self.assertTrue(path.exists())
        with patch.object(self.studio,'metadata',return_value={'title':'\u041a\u043e\u043f\u0438\u044f','tags':'\u0442\u0435\u0441\u0442','category':'Effect'}):
            result=self.studio.commit({'draft_id':draft['draft_id']},self.job)
            again=self.studio.commit({'draft_id':draft['draft_id']},self.job)
        self.assertEqual(result['item']['id'],again['item']['id']);self.assertEqual(len(self.library.items()),2)
        self.studio.undo(draft['draft_id']);self.assertEqual(len(self.library.items()),1);self.assertTrue(self.library.path(self.item['id']).exists())
    def test_cancel_draft(self):
        draft=self.studio.render({'id':self.item['id'],'start':0,'end':1},self.job)
        _,path=self.studio.draft(draft['draft_id']);self.studio.discard(draft['draft_id'])
        self.assertFalse(path.exists());self.assertEqual(len(self.library.items()),1)
    def test_unknown_ai_operation(self):
        with self.assertRaises(ValueError):self.studio.submit({'kind':'execute_arbitrary_shell'})
    def test_external_search_expands_when_only_unusable_files_found(self):
        blocked={'source_id':'commons:1','can_import':False}
        usable={'source_id':'commons:2','can_import':True}
        with patch.object(self.studio.models,'generate',return_value={'search_terms':'electronic signal short'}), \
             patch.object(self.studio.catalog,'search',side_effect=[[blocked],[usable,blocked]]) as search:
            result=self.studio.search({'query':'\u043a\u043e\u0440\u043e\u0442\u043a\u0438\u0439 \u0441\u0438\u0433\u043d\u0430\u043b','local':False,'external':True},self.job)
        self.assertEqual(search.call_args.args[0],'electronic OR signal')
        self.assertEqual(result['external'],[usable,blocked])
        self.assertTrue(result['warnings'])
    def test_full_attribution_survives_a_derived_copy(self):
        license=json.dumps({'license':'CC BY-SA 4.0','author':'Author '*300,'page_url':'https://commons.wikimedia.org/wiki/File:Example.wav'})
        self.library.edit(self.item['id'],{'license':license})
        draft=self.studio.render({'id':self.item['id'],'start':0,'end':1},self.job)
        with patch.object(self.studio,'metadata',return_value={'title':'\u041a\u043e\u043f\u0438\u044f','tags':'\u0442\u0435\u0441\u0442','category':'Effect'}):
            result=self.studio.commit({'draft_id':draft['draft_id']},self.job)
        self.assertEqual(result['item']['license'],license)
    def test_subframe_audio_features_keep_real_duration(self):
        import wave,struct
        from mimic.features import analyze
        file=self.root/'tiny.wav'
        with wave.open(str(file),'wb') as wav:
            wav.setparams((1,2,8000,0,'NONE','not compressed'));wav.writeframes(struct.pack('<'+'h'*80,*([1000]*80)))
        data=analyze(file)
        self.assertAlmostEqual(data['duration'],.01,places=3)
        self.assertGreater(data['rms'],.02)

if __name__=='__main__':unittest.main()
