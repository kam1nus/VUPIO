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
 def spec(self,*a):return {'sha256':'fixture'}
class WebAgentTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.settings=SearchSettings(Library(self.tmp.name))
 def test_settings_secret_not_returned_and_private_file(self):
  secret='tvly-unit-test-key';r=self.settings.save(secret)
  self.assertNotIn(secret,json.dumps(r));self.assertTrue(r['has_key'])
  if os.name!='nt':self.assertEqual(self.settings.path.stat().st_mode&0o777,0o600)
  self.settings.save('');self.assertFalse(self.settings.status()['has_key'])
 def test_keyless_request_real_endpoint_basic_only(self):
  opener=MagicMock();opener.open.return_value=io.BytesIO(json.dumps({'results':[{'url':'https://example.org/sound','title':'Emotional Damage','score':.9,'content':'A real search result'},{'url':'file:///etc/passwd','title':'bad'}]}).encode())
  with patch('mimic.web_agent.build_opener',return_value=opener),patch.dict(os.environ,{'MIMIC_TAVILY_KEY':''}):
   rows=Tavily(self.settings).search('emotional damage')
  req=opener.open.call_args.args[0];body=json.loads(req.data)
  self.assertEqual(req.full_url,'https://api.tavily.com/search');self.assertIn('keyless',req.headers.values());self.assertNotIn('Authorization',req.headers)
  self.assertEqual(body['search_depth'],'basic');self.assertFalse(body['auto_parameters']);self.assertEqual(len(rows),1);self.assertTrue(rows[0]['can_import']);self.assertFalse(rows[0]['rights_checked'])
  self.assertEqual(Tavily(self.settings).usage(),{'mode':'keyless','requests':1})
 def test_usage_respects_both_plan_and_key_limits(self):
  self.settings.save('tvly-unit-test-key')
  opener=MagicMock()
  opener.open.return_value=io.BytesIO(json.dumps({
   'account':{'plan_usage':120,'plan_limit':1000},'key':{'usage':60,'limit':100},
  }).encode())
  with patch('mimic.web_agent.build_opener',return_value=opener):usage=Tavily(self.settings).usage()
  request=opener.open.call_args.args[0]
  self.assertEqual(request.full_url,'https://api.tavily.com/usage')
  self.assertEqual(request.headers['Authorization'],'Bearer tvly-unit-test-key')
  self.assertEqual(usage,{'mode':'own-key','remaining':40,'used':120,'limit':1000})
 def test_quota_is_not_silent_paid_fallback(self):
  opener=MagicMock();opener.open.side_effect=HTTPError('https://api.tavily.com/search',429,'rate limited',{},None)
  with patch('mimic.web_agent.build_opener',return_value=opener):
   with self.assertRaisesRegex(ValueError,'too many requests'):Tavily(self.settings).search('test')
  self.assertEqual(opener.open.call_count,1)
 def finder(self,model=None):
  class Studio:pass
  s=Studio();s.library=Library(self.tmp.name);s.models=model or NoModel();s.finder=Finder(s);return s.finder
 def test_web_scope_does_not_fall_back_to_catalogs(self):
  f=self.finder();real=web_row('https://example.org/audio.mp3','Emotional Damage','Tavily')
  with patch.object(f.web.provider,'search',return_value=[real]) as search,patch.object(f.providers['commons'],'search',side_effect=AssertionError('catalog called')):
   r=f.search({'scope':'web','query':'\u043d\u0430\u0439\u0434\u0438 \u043c\u0435\u043c emotional damage','category':'Meme'},Job())
  self.assertEqual(r['scope'],'web');self.assertEqual(len(r['external']),1);self.assertIn('emotional damage',search.call_args.args[0]);self.assertEqual(f.saved(real['source_id'])['title'],'Emotional Damage')
 def test_model_cannot_invent_results_or_download_permission(self):
  class Model(NoModel):
   def path(self,*a):return Path('/unused')
   def generate(self,*args):return {'ranking':[{'id':'invented','score':1,'url':'https://evil.example'},{'id':'0','score':.9,'reason':'reaction','can_import':True}]}
  f=self.finder(Model());real=web_row('https://example.org/audio.mp3','Emotional Damage','Tavily')
  with patch.object(f.web.provider,'search',return_value=[real]):r=f.search({'scope':'web','query':'\u043d\u0430\u0439\u0434\u0438 \u043c\u0435\u043c emotional damage'},Job())
  self.assertEqual(len(r['external']),1);self.assertEqual(r['external'][0]['page_url'],'https://example.org/audio.mp3');self.assertTrue(r['external'][0]['can_import']);self.assertFalse(r['external'][0]['rights_checked']);self.assertNotIn('https://evil.example',json.dumps(r));self.assertTrue(r['ai_ranked'])
 def test_empty_ai_ranking_does_not_erase_web_results(self):
  class Model(NoModel):
   def path(self,*a):return Path('/unused')
   def generate(self,*args):return {'ranking':[]}
  f=self.finder(Model());real=web_row('https://example.org/audio.mp3','Emotional Damage','Tavily')
  with patch.object(f.web.provider,'search',return_value=[real]):r=f.search({'scope':'web','query':'\u043d\u0430\u0439\u0434\u0438 \u043c\u0435\u043c emotional damage'},Job())
  self.assertEqual(len(r['external']),1);self.assertFalse(r['ai_ranked'])

 def test_cyrillic_search_falls_back_to_sound_sites_and_marks_player_links(self):
  f=self.finder()
  video=web_row('https://www.youtube.com/watch?v=example','\u041c\u0438\u0448\u0430','Tavily')
  sound=web_row('https://www.myinstants.com/ru/instant/misha/','\u0414\u0430\u0432\u0430\u0439 \u043f\u043e \u043d\u043e\u0432\u043e\u0439 \u041c\u0438\u0448\u0430','Tavily')
  with patch.object(f.web.provider,'search',side_effect=[[video],[sound]]) as search:
   result=f.search({'scope':'web','query':'\u041d\u0430\u0439\u0434\u0438 \u043c\u0435\u043c \u0414\u0430\u0432\u0430\u0439 \u043f\u043e \u043d\u043e\u0432\u043e\u0439, \u041c\u0438\u0448\u0430'},Job())
  self.assertIn('\u0414\u0430\u0432\u0430\u0439 \u043f\u043e \u043d\u043e\u0432\u043e\u0439, \u041c\u0438\u0448\u0430',search.call_args_list[0].args[0])
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
  button=web_row('https://www.myinstants.com/ru/instant/arsen-markarian/', '\u0410\u0440\u0441\u0435\u043d \u041c\u0430\u0440\u043a\u0430\u0440\u044f\u043d', 'Tavily')
  duplicate=web_row('https://www.myinstants.com/en/instant/arsen-markarian/', '\u0410\u0440\u0441\u0435\u043d \u041c\u0430\u0440\u043a\u0430\u0440\u044f\u043d', 'Tavily')
  quote=web_row('https://uwupad.me/sound/66116', '\u041e \u0433\u043e\u0441\u043f\u043e\u0434\u0438 \u0410\u0440\u0441\u0435\u043d \u041c\u0430\u0440\u043a\u0430\u0440\u044f\u043d', 'Tavily')
  collection=web_row('https://example.org/memes', '\u041c\u0435\u043c\u044b \u0441 \u0410\u0440\u0441\u0435\u043d\u043e\u043c \u041c\u0430\u0440\u043a\u0430\u0440\u044f\u043d\u043e\u043c', 'Tavily')
  unrelated=web_row('https://example.org/cat.mp3', '\u041a\u043e\u0442 \u043c\u044f\u0443\u043a\u0430\u0435\u0442', 'Tavily')

  def search(query, domains=None):
   if domains:
    self.assertEqual(query,'\u0410\u0440\u0441\u0435\u043d \u041c\u0430\u0440\u043a\u0430\u0440\u044f\u043d')
    return [button,quote,unrelated]
   self.assertIn('\u0410\u0440\u0441\u0435\u043d \u041c\u0430\u0440\u043a\u0430\u0440\u044f\u043d \u043c\u0435\u043c\u044b',query)
   return [duplicate,collection]

  with patch.object(f.web.provider,'search',side_effect=search):
   result=f.search({'scope':'web','query':'\u041c\u0435\u043c\u044b \u0441 \u0410\u0440\u0441\u0435\u043d\u043e\u043c \u041c\u0430\u0440\u043a\u0430\u0440\u044f\u043d\u043e\u043c'},Job())
  self.assertTrue(result['topic_search'])
  self.assertEqual(result['external'],[button,quote,collection])
  self.assertEqual([r['can_import'] for r in result['external']],[True,True,False])

 def test_multilingual_queries_keep_original_text_with_optional_english_expansion(self):
  class Model(NoModel):
   def path(self,*args):return Path('/unused')
   def generate(self,prompt,text,*args):
    return {'search_terms':'screaming cat'} if 'search_terms' in prompt else {'ranking':[]}
  queries=[
   '\u043d\u0430\u0439\u0434\u0438 \u0437\u0432\u0443\u043a \u043a\u043e\u0442\u0430', 'encuentra un gato gritando', 'procure gato gritando',
   'suche eine schreiende Katze', '猫の叫び声', '寻找猫叫声',
  ]
  for query in queries:
   with self.subTest(query=query):
    finder=self.finder(Model())
    real=web_row('https://example.org/cat.mp3','Cat','Tavily')
    with patch.object(finder.web.provider,'search',side_effect=[[],[real]]) as search:
     found=finder.search({'scope':'web','query':query},Job())
    first=search.call_args_list[0].args[0]
    self.assertIn(query.split()[-1],first)
    self.assertTrue(any('screaming cat' in call.args[0] for call in search.call_args_list))
    self.assertEqual(found['query'],query)
    self.assertEqual(found['external'][0]['page_url'],real['page_url'])

 def test_fast_results_are_saved_before_ranking_and_repeat_uses_cache(self):
  real=web_row('https://example.org/cat.mp3','Cat','Tavily')
  class Model(NoModel):
   def path(self,*args):return Path('/unused')
   def generate(self,prompt,text,*args):
    self_test.assertEqual(finder.saved(real['source_id'])['title'],'Cat')
    job.publish.assert_called_once()
    self_test.assertNotIn('search_terms',prompt)
    return {'ranking':[{'id':'0','score':.9}]}
  self_test=self
  finder=self.finder(Model())
  job=Job()
  job.publish=MagicMock()
  query={'scope':'web','query':'cat sound','progressive':True}
  with patch.object(finder.web.provider,'search',return_value=[real]) as search:
   first=finder.search(query,job)
   second=finder.search(query,job)
  search.assert_called_once()
  self.assertTrue(first['ai_ranked'])
  self.assertTrue(second['cached'])
  self.assertEqual(first['external'],second['external'])

 def test_topics_in_multiple_languages_preserve_person_names(self):
  from mimic.web_agent import topic_subject
  for query in ['memes with Keanu Reeves','memes con Keanu Reeves',
                'memes sobre Keanu Reeves','mèmes avec Keanu Reeves','Memes mit Keanu Reeves']:
   with self.subTest(query=query):
    self.assertEqual(topic_subject(query),'Keanu Reeves')
