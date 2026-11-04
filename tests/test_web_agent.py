import unittest,tempfile,json,io,os
from pathlib import Path
from unittest.mock import patch,MagicMock
from urllib.error import HTTPError
from mimic.web_agent import SearchSettings,Tavily,web_row
from mimic.finder import Finder,row
from mimic.library import Library
class Job:
 def check(self):pass
 def update(self,*a):pass
class NoModel:
 def path(self,*a):raise ValueError('No model')
class WebAgentTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.settings=SearchSettings(self.tmp.name)
 def test_settings_secret_not_returned_and_private_file(self):
  secret='tvly-unit-test-key';r=self.settings.save(secret)
  self.assertNotIn(secret,json.dumps(r));self.assertTrue(r['has_key']);self.assertEqual(self.settings.path.stat().st_mode&0o777,0o600)
  self.settings.save('');self.assertFalse(self.settings.status()['has_key'])
 def test_keyless_request_real_endpoint_basic_only(self):
  opener=MagicMock();opener.open.return_value=io.BytesIO(json.dumps({'results':[{'url':'https://example.org/sound','title':'Emotional Damage','score':.9,'content':'A real search result'},{'url':'file:///etc/passwd','title':'bad'}]}).encode())
  with patch('mimic.web_agent.build_opener',return_value=opener),patch.dict(os.environ,{},clear=True):
   rows=Tavily(self.settings).search('emotional damage')
  req=opener.open.call_args.args[0];body=json.loads(req.data)
  self.assertEqual(req.full_url,'https://api.tavily.com/search');self.assertIn('keyless',req.headers.values());self.assertNotIn('Authorization',req.headers)
  self.assertEqual(body['search_depth'],'basic');self.assertFalse(body['auto_parameters']);self.assertEqual(len(rows),1);self.assertTrue(rows[0]['can_import']);self.assertFalse(rows[0]['rights_checked'])
 def test_quota_is_not_silent_paid_fallback(self):
  opener=MagicMock();opener.open.side_effect=HTTPError('https://api.tavily.com/search',429,'rate limited',{},None)
  with patch('mimic.web_agent.build_opener',return_value=opener):
   with self.assertRaisesRegex(ValueError,'Лимит бесплатного'):Tavily(self.settings).search('test')
  self.assertEqual(opener.open.call_count,1)
 def finder(self,model=None):
  class Studio:pass
  s=Studio();s.library=Library(self.tmp.name);s.models=model or NoModel();s.finder=Finder(s);return s.finder
 def test_web_scope_does_not_fall_back_to_catalogs(self):
  f=self.finder();real=web_row('https://example.org/audio.mp3','Emotional Damage','Tavily')
  with patch.object(f.web.provider,'search',return_value=[real]) as search,patch.object(f.providers['commons'],'search',side_effect=AssertionError('catalog called')):
   r=f.search({'scope':'web','query':'найди мем emotional damage','category':'Meme'},Job())
  self.assertEqual(r['scope'],'web');self.assertEqual(len(r['external']),1);self.assertIn('emotional damage',search.call_args.args[0]);self.assertEqual(f.saved(real['source_id'])['title'],'Emotional Damage')
 def test_model_cannot_invent_results_or_download_permission(self):
  class Model:
   def path(self,*a):return Path('/unused')
   def generate(self,*args):return {'ranking':[{'id':'invented','score':1,'url':'https://evil.example'},{'id':'0','score':.9,'reason':'reaction','can_import':True}]}
  f=self.finder(Model());real=web_row('https://example.org/audio.mp3','Emotional Damage','Tavily')
  with patch.object(f.web.provider,'search',return_value=[real]):r=f.search({'scope':'web','query':'найди мем emotional damage'},Job())
  self.assertEqual(len(r['external']),1);self.assertEqual(r['external'][0]['page_url'],'https://example.org/audio.mp3');self.assertTrue(r['external'][0]['can_import']);self.assertFalse(r['external'][0]['rights_checked']);self.assertNotIn('https://evil.example',json.dumps(r));self.assertTrue(r['ai_ranked'])
 def test_empty_ai_ranking_does_not_erase_web_results(self):
  class Model:
   def path(self,*a):return Path('/unused')
   def generate(self,*args):return {'ranking':[]}
  f=self.finder(Model());real=web_row('https://example.org/audio.mp3','Emotional Damage','Tavily')
  with patch.object(f.web.provider,'search',return_value=[real]):r=f.search({'scope':'web','query':'найди мем emotional damage'},Job())
  self.assertEqual(len(r['external']),1);self.assertFalse(r['ai_ranked'])

 def test_cyrillic_search_falls_back_to_sound_sites_and_marks_player_links(self):
  f=self.finder()
  video=web_row('https://www.youtube.com/watch?v=example','Миша','Tavily')
  sound=web_row('https://www.myinstants.com/ru/instant/misha/','Давай по новой Миша','Tavily')
  with patch.object(f.web.provider,'search',side_effect=[[video],[sound]]) as search:
   result=f.search({'scope':'web','query':'Найди мем Давай по новой, Миша'},Job())
  self.assertIn('Давай по новой, Миша',search.call_args_list[0].args[0])
  self.assertIn('myinstants.com',search.call_args_list[1].kwargs['domains'])
  self.assertEqual([r['can_import'] for r in result['external']],[True,False])
  self.assertFalse(f.saved(video['source_id'])['can_import'])

 def test_pasted_audio_link_never_leaves_for_web_search_or_history(self):
  f=self.finder()
  url='https://example.org/meme.mp3?token=example'
  with patch.object(f.web.provider,'search',side_effect=AssertionError('Private URL sent to Tavily')):
   r=f.search({'scope':'web','query':url},Job())
  self.assertEqual(r['history'],[])
  self.assertEqual(f.saved(r['external'][0]['source_id'])['page_url'],url)
  self.assertTrue(r['external'][0]['can_import'])

 def test_topic_returns_distinct_clips_and_labels_collections_as_links(self):
  f=self.finder()
  button=web_row('https://www.myinstants.com/ru/instant/arsen-markarian/', 'Арсен Маркарян', 'Tavily')
  duplicate=web_row('https://www.myinstants.com/en/instant/arsen-markarian/', 'Арсен Маркарян', 'Tavily')
  quote=web_row('https://uwupad.me/sound/66116', 'О господи Арсен Маркарян', 'Tavily')
  collection=web_row('https://example.org/memes', 'Мемы с Арсеном Маркаряном', 'Tavily')
  unrelated=web_row('https://example.org/cat.mp3', 'Кот мяукает', 'Tavily')

  def search(query, domains=None):
   if domains:
    self.assertEqual(query,'Арсен Маркарян')
    return [button,quote,unrelated]
   self.assertIn('Арсен Маркарян мемы',query)
   return [duplicate,collection]

  with patch.object(f.web.provider,'search',side_effect=search):
   result=f.search({'scope':'web','query':'Мемы с Арсеном Маркаряном'},Job())
  self.assertTrue(result['topic_search'])
  self.assertEqual(result['external'],[button,quote,collection])
  self.assertEqual([r['can_import'] for r in result['external']],[True,True,False])
