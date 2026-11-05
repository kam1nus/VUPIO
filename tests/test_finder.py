import unittest,tempfile,json,wave,struct
from pathlib import Path
from unittest.mock import patch
from mimic.finder import permitted_license,fallback_terms,Finder,Archive,Brave
from mimic.autofetch import cut_plan
from mimic.library import Library
from mimic.jobs import Cancelled

class Job:
 def check(self):pass
 def update(self,*a):pass
class Models:
 def path(self,*a):raise ValueError('not installed')
class Provider:
 def search(self,q):return [dict(source_id='fake:1',title='Scream',description='scream reaction',page_url='https://example.org/s',can_import=True,download_url='https://example.org/audio')]
class FinderTests(unittest.TestCase):
 def test_license_allowlist(self):
  for url in ['https://creativecommons.org/licenses/by/4.0/','http://creativecommons.org/licenses/by-sa/3.0/','https://creativecommons.org/publicdomain/zero/1.0/']:self.assertTrue(permitted_license(url))
  for url in ['https://creativecommons.org/licenses/by-nc/4.0/','https://evil.org/licenses/by/4.0/','https://creativecommons.org.evil.org/licenses/by/4.0/','https://creativecommons.org/licenses/by-nd/4.0/','']:self.assertFalse(permitted_license(url))
 def test_russian_terms(self):self.assertEqual(fallback_terms('\u041d\u0430\u0439\u0434\u0438 \u043c\u0435\u043c \u0441 \u043d\u0435\u043e\u0436\u0438\u0434\u0430\u043d\u043d\u044b\u043c \u043a\u0440\u0438\u043a\u043e\u043c'),'scream')
 def test_exact_name(self):self.assertEqual(fallback_terms('\u041d\u0430\u0439\u0434\u0438 Wide Putin'),'Wide Putin')
 def test_relative_cut(self):
  p=cut_plan('\u043d\u0430\u0447\u043d\u0438 \u0440\u0430\u043d\u044c\u0448\u0435 \u043d\u0430 \u043e\u0434\u043d\u0443 \u0441\u0435\u043a\u0443\u043d\u0434\u0443',10,{},dict(start=3,end=6));self.assertEqual((p['start'],p['end']),(2,6))
 def test_duration(self):self.assertEqual(cut_plan('\u0441\u0434\u0435\u043b\u0430\u0439 \u043d\u0430 \u0442\u0440\u0438 \u0441\u0435\u043a\u0443\u043d\u0434\u044b',20,{})['end'],3)
 def test_uncertain_recognizable(self):self.assertTrue(cut_plan('\u043e\u0441\u0442\u0430\u0432\u044c \u0443\u0437\u043d\u0430\u0432\u0430\u0435\u043c\u0443\u044e \u0447\u0430\u0441\u0442\u044c',20,{})['warning'])
 def test_no_false_scream(self):
  with self.assertRaises(ValueError):cut_plan('\u043d\u0430\u0447\u043d\u0438 \u0434\u043e \u043a\u0440\u0438\u043a\u0430',5,{'features':{'onsets':[]}})
 def test_timestamp_scream(self):
  p=cut_plan('\u043d\u0430\u0447\u043d\u0438 \u0434\u043e \u043a\u0440\u0438\u043a\u0430',10,{'windows':[{'start':4,'end':6,'labels':[{'label':'scream','confidence':.8}]}]});self.assertEqual((p['start'],p['end']),(3,9))
 def test_phrase(self):
  p=cut_plan('\u043e\u0441\u0442\u0430\u0432\u044c \u0444\u0440\u0430\u0437\u0443 «what»',5,{'segments':[dict(start=2,end=3,text='what')]});self.assertEqual((p['start'],p['end']),(1.9,3.15))
 def test_invalid_relative(self):
  with self.assertRaises(ValueError):cut_plan('\u043e\u0431\u0440\u0435\u0436\u044c \u043a\u043e\u043d\u0435\u0446 \u043d\u0430 \u0434\u0435\u0441\u044f\u0442\u044c \u0441\u0435\u043a\u0443\u043d\u0434',5,{})
 def test_merge_history_missing_provider(self):
  with tempfile.TemporaryDirectory() as d:
   class Studio:pass
   s=Studio();s.library=Library(d);s.models=Models();f=Finder(s)
   class Bad:
    def search(self,q):raise ValueError('offline')
   f.providers={'one':Provider(),'two':Provider(),'bad':Bad()}
   r=f.search({'query':'\u043a\u0440\u0438\u043a'},Job());self.assertEqual(len(r['external']),1);self.assertEqual(r['providers']['bad'],0);self.assertEqual(f.history(),['\u043a\u0440\u0438\u043a']);self.assertEqual(f.saved('fake:1')['title'],'Scream')
 def test_brave_unconfigured(self):
  with patch.dict('os.environ',{},clear=True):
   with self.assertRaises(ValueError):Brave().search('test')
 def test_download_reject_private_and_arbitrary(self):
  from mimic.net import catalog_download
  with tempfile.TemporaryDirectory() as d:
   for url in ['http://archive.org/a','https://127.0.0.1/a','https://evil.org/a','https://archive.org:444/a','https://a:b@archive.org/a']:
    with self.assertRaises(ValueError):catalog_download(url,Path(d)/'a')
 def test_archive_identity(self):
  with self.assertRaises(ValueError):Archive().resolve('archive:../../private')
 def test_cancel_does_not_retry(self):
  from mimic.autofetch import AutoFetch
  class Studio:pass
  s=Studio()
  class FakeFinder:
   def search(self,b,j):return {'external':[dict(source_id='x',can_import=True)],'warnings':[],'history':[]}
  s.finder=FakeFinder();a=AutoFetch(s)
  with patch.object(a,'prepare',side_effect=Cancelled('cancel')):
   with self.assertRaises(Cancelled):a.quick({},Job())

class DownloadVerificationTests(unittest.TestCase):
 def test_invalid_file_cannot_enter_library(self):
  from mimic.studio import Studio
  with tempfile.TemporaryDirectory() as d:
   s=Studio(Library(d),'/not-used')
   source={'source_id':'commons:1','can_import':True,'download_url':'https://upload.wikimedia.org/a','title':'Scream','description':'','license':'CC0'}
   def malicious(url,path,*args):path.write_text('#!/bin/sh\necho notaudio')
   try:
    with patch.object(s.finder,'saved',return_value={'query':'scream','terms':'scream'}),patch.object(s.finder,'resolve',return_value=source),patch('mimic.autofetch.catalog_download',side_effect=malicious):
     with self.assertRaises(ValueError):s.autofetch.prepare({'source_id':'commons:1'},Job())
    self.assertEqual(s.library.items(),[]);self.assertEqual(list(s.cache.iterdir()),[])
   finally:s.close()
 def test_silent_file_rejected(self):
  from mimic.studio import Studio
  with tempfile.TemporaryDirectory() as d:
   s=Studio(Library(d),'/not-used')
   source={'source_id':'commons:1','can_import':True,'download_url':'https://upload.wikimedia.org/a','title':'Scream','description':'','license':'CC0'}
   def silence(url,path,*args):
    with wave.open(str(path),'wb') as f:f.setparams((1,2,16000,0,'NONE','not compressed'));f.writeframes(b'\0\0'*32000)
   try:
    with patch.object(s.finder,'saved',return_value={'query':'scream','terms':'scream'}),patch.object(s.finder,'resolve',return_value=source),patch('mimic.autofetch.catalog_download',side_effect=silence):
     with self.assertRaisesRegex(ValueError,'silence'):s.autofetch.prepare({'source_id':'commons:1'},Job())
    self.assertEqual(s.library.items(),[]);self.assertEqual(list(s.cache.iterdir()),[])
   finally:s.close()

class QueryRegressionTests(unittest.TestCase):
 def test_model_cannot_obscure_known_event(self):
  with tempfile.TemporaryDirectory() as d:
   class Studio:pass
   class MisleadingModel:
    def path(self,k):return Path('/unused')
    def generate(self,*args):return {'search_terms':'surprise reaction meme'}
   class CaptureProvider(Provider):
    def search(self,q):self.query=q;return super().search(q)
   s=Studio();s.library=Library(d);s.models=MisleadingModel();f=Finder(s);p=CaptureProvider();f.providers={'test':p}
   f.search({'query':'\u041d\u0430\u0439\u0434\u0438 \u043c\u0435\u043c \u0441 \u043d\u0435\u043e\u0436\u0438\u0434\u0430\u043d\u043d\u044b\u043c \u043a\u0440\u0438\u043a\u043e\u043c'},Job());self.assertEqual(p.query,'scream')

class FractionalDurationTests(unittest.TestCase):
 def test_rounding_does_not_overrun_short_file(self):
  d=1.619592
  p=cut_plan('\u0421\u0434\u0435\u043b\u0430\u0439 \u043d\u0430 \u0442\u0440\u0438 \u0441\u0435\u043a\u0443\u043d\u0434\u044b',d,{})
  self.assertLessEqual(p['end'],d)

class ScreenshotSearchRegressionTests(unittest.TestCase):
 def search(self,providers,query='\u043d\u0430\u0439\u0434\u0438 \u043c\u0435\u043c emotional damage',category='Meme',models=None):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
  class Studio:pass
  s=Studio();s.library=Library(temp.name);s.models=models or Models();f=Finder(s);f.providers=providers
  return f.search({'query':query,'category':category},Job())
 def test_english_meme_title_preserved(self):
  from mimic.finder import named_terms
  self.assertEqual(named_terms('\u043d\u0430\u0439\u0434\u0438 \u043c\u0435\u043c emotional damage'),'emotional damage')
  self.assertEqual(fallback_terms('\u043d\u0430\u0439\u0434\u0438 \u043c\u0435\u043c emotional damage'),'emotional damage')
  self.assertEqual(fallback_terms('\u041d\u0430\u0439\u0434\u0438 emotional damage'),'emotional damage')
 def test_meme_filter_keeps_emotional_damage_without_word_meme(self):
  class Emotional(Provider):
   def search(self,q):return [dict(source_id='fake:emotional',title='Emotional Damage',description='reaction',page_url='https://example.org/emotional',can_import=False)]
  r=self.search({'catalog':Emotional()})
  self.assertEqual(len(r['external']),1);self.assertTrue(r['external'][0]['named_query']);self.assertIn('Results: 1',r['status_message'])
 def test_empty_result_is_not_ready_with_results(self):
  class Empty:
   def search(self,q):return []
  r=self.search({'catalog':Empty()});self.assertEqual(r['external'],[]);self.assertIn('No catalog matches',r['status_message'])
 def test_disabled_brave_is_not_an_outage(self):
  with patch.dict('os.environ',{},clear=True):
   r=self.search({'brave':Brave(),'catalog':Provider()})
  self.assertEqual(r['provider_status']['brave'],'disabled');self.assertTrue(r['notices']);self.assertFalse(any('brave:' in x for x in r['warnings']))
 def test_model_cannot_add_english_audio_to_title(self):
  class MisleadingModel:
   def path(self,k):return Path('/unused')
   def generate(self,*args):return {'search_terms':'emotional damage english audio'}
  class Capture(Provider):
   def search(self,q):self.query=q;return super().search(q)
  p=Capture();self.search({'catalog':p},models=MisleadingModel());self.assertEqual(p.query,'emotional damage')
