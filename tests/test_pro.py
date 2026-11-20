"""Pro collection orchestration: access, real library data, review and safe retries."""
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from mimic.library import Library
from mimic.pro import ProStudio, identity
from mimic.jobs import Cancelled

class Job:
    def check(self): pass
    def update(self,*args): pass
    def publish(self,*args): pass

class ProTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.lib=Library(temp.name)
        with self.lib.db() as db:
            for id,title in [('one','Funny racing crash'),('two','Racing victory'),('three','Quiet waterfall')]:
                (self.lib.files/(id+'.wav')).write_bytes(b'audio fixture')
                db.execute('INSERT INTO clips VALUES (?,?,?,?,?,0,?,?,?)',(id,title,'Meme','racing' if id!='three' else 'nature','',1,id+'.wav',''))
        models=SimpleNamespace(generate=Mock(side_effect=ValueError('Offline')),embed=Mock(side_effect=ValueError('Offline')))
        self.finder=Mock();self.finder.search.return_value={'external':[]}
        self.studio=SimpleNamespace(library=self.lib,models=models,finder=self.finder,changed=Mock(),autofetch=Mock(),asset=Mock())
        self.require=Mock();self.pro=ProStudio(self.studio,self.require);self.job=Job()
    def generate(self,**body):return self.pro.generate({'brief':'racing','local':True,'web':False,**body},self.job)
    def test_access_before_network_or_model_and_free_reads(self):
        self.require.side_effect=ValueError('Pro required')
        with self.assertRaises(ValueError):self.generate(web=True)
        self.finder.search.assert_not_called();self.studio.models.generate.assert_not_called()
        self.assertEqual(self.pro.status()['topics'],[])
    def test_metadata_fallback_filters_unrelated_and_preserves_multilingual_brief(self):
        data=self.generate()
        self.assertEqual({r['local_id'] for r in data['rows']},{'one','two'})
        self.assertEqual(data['mode'],'metadata');self.assertTrue(data['notices'])
        self.assertEqual(self.pro.get(data['id'])['rows'],data['rows'])
        self.assertEqual(self.lib.boards(),[])
    def test_topics_refresh_and_feedback_are_persistent(self):
        topic=self.pro.save_topic({'title':'Racing','query':'racing','region':'us','category':'Meme'})
        first=self.generate(topic_id=topic['id']);self.assertTrue(all(r['new'] for r in first['rows']))
        hidden=first['rows'][0]['key'];self.pro.feedback(hidden,'hide')
        second=self.generate(topic_id=topic['id'])
        self.assertNotIn(hidden,{r['key'] for r in second['rows']});self.assertTrue(all(not r['new'] for r in second['rows']))
        self.assertEqual(ProStudio(self.studio,self.require).status()['topics'][0]['collection_id'],second['id'])
        self.pro.delete_topic(topic['id']);self.assertEqual(self.pro.status()['topics'],[])
    def external(self,count=4):
        self.finder.search.return_value={'external':[{'title':'Racing reaction '+str(i),'source_id':str(i),'page_url':'https://example.org/'+str(i),'source':'Fixture source'} for i in range(count)]}
        return self.generate(local=False,web=True,count=2)
    def test_model_ids_cannot_invent_sources_or_duplicate_candidates(self):
        self.studio.models.generate.side_effect=[{'queries':[{'query':'мемы гонки'}],'title':'Гонки'},{'ranking':[{'id':'https://bad.test'},{'id':'999'},{'id':'0','reason':'Racing'},{'id':'0'}]}]
        data=self.external()
        self.assertEqual(len(data['rows']),1);self.assertEqual(len(data['pool']),3)
        self.assertTrue(self.finder.search.call_args.args[0]['query'].startswith('мемы гонки'))
        self.assertEqual(data['rows'][0]['source_id'],'0')
    def test_prepare_does_not_import_reports_errors_and_correct_duration(self):
        data=self.external();self.studio.autofetch.prepare.side_effect=[{'asset_id':'asset','preview_url':'/api/ai/asset/asset','report':{'duration':60,'output':{'duration':8},'plan':{'start':0,'end':8}}},ValueError('HTTP 404')]
        prepared=self.pro.prepare({'id':data['id'],'keys':[r['key'] for r in data['rows']]},self.job)
        self.assertEqual(prepared['rows'][0]['duration'],8);self.assertTrue(prepared['rows'][0]['ready'])
        self.assertFalse(prepared['rows'][1]['ready']);self.assertIn('404',prepared['rows'][1]['error'])
        self.studio.autofetch.commit.assert_not_called();self.assertEqual(len(self.lib.items()),3)
        with self.assertRaises(ValueError):self.pro.create_board({'id':data['id'],'keys':[r['key'] for r in data['rows']]},self.job)
    def test_reviewed_board_reuses_library_and_is_idempotent(self):
        data=self.generate();body={'id':data['id'],'keys':[r['key'] for r in data['rows']]}
        first=self.pro.create_board(body,self.job);second=self.pro.create_board(body,self.job)
        self.assertEqual(first['board_id'],second['board_id']);self.assertEqual(len(self.lib.boards()),1)
        self.assertEqual(len(self.lib.items()),3);self.studio.autofetch.commit.assert_not_called()
    def test_partial_import_retry_does_not_commit_same_asset_twice(self):
        data=self.external()
        for i,row in enumerate(data['rows']):row.update(ready=True,asset_id=str(i))
        self.pro._save(data);body={'id':data['id'],'keys':[r['key'] for r in data['rows']]}
        self.studio.autofetch.commit.side_effect=[{'item':self.lib.get('one')},ValueError('Source expired')]
        with self.assertRaises(ValueError):self.pro.create_board(body,self.job)
        self.assertEqual(self.lib.boards(),[])
        self.studio.autofetch.commit.side_effect=None;self.studio.autofetch.commit.return_value={'item':self.lib.get('two')}
        result=self.pro.create_board(body,self.job)
        self.assertEqual(self.studio.autofetch.commit.call_count,3);self.assertEqual(result['count'],2)
    def test_replace_uses_real_pool_and_deleted_library_clip_is_marked(self):
        data=self.external();new=self.pro.replace(data['id'],data['rows'][0]['key'])
        self.assertEqual(new['rows'][0]['source_id'],'2')
        local=self.generate();row=local['rows'][0];self.lib.delete(row['local_id'])
        prepared=self.pro.prepare({'id':local['id'],'keys':[row['key']]},self.job)
        self.assertFalse(prepared['rows'][0]['ready']);self.assertIn('deleted',prepared['rows'][0]['error'])
    def test_cancelled_job_never_creates_collection(self):
        job=Job();job.check=Mock(side_effect=Cancelled('Cancelled'))
        with self.assertRaises(Cancelled):self.pro.generate({'brief':'racing'},job)
        self.assertEqual(self.pro.status()['collections'],[])
    def test_bad_selection_and_parameters(self):
        data=self.generate()
        for keys in [[],['missing'],[{}],'all']:
            with self.assertRaises(ValueError):self.pro.prepare({'id':data['id'],'keys':keys},self.job)
        for body in [{'count':True},{'region':'invalid'},{'local':False,'web':False},{'brief':''}]:
            with self.assertRaises(ValueError):self.generate(**body)
        with self.assertRaises(ValueError):self.pro.feedback('bad','hide')
        self.assertEqual(identity({'page_url':'https://EXAMPLE.org/foo/#anchor'}),identity({'page_url':'https://example.org/foo'}))
