"""Two local profiles exchange real encoded audio; no physical microphone is opened."""
import copy,hashlib,json,shutil,tempfile,unittest,io
from pathlib import Path
from unittest.mock import Mock,patch
from mimic.library import Library
from mimic.studio import Studio
from mimic.sharing import Sharing,Cloud,SharingConflict,parse_link
from mimic.account import WEBSITE,AccountService
from test_mimic import tone
from test_pro import Job

class MemoryCloud:
    def __init__(self):self.assets={};self.boards={};self.drops={};self.uploads=0
    def call(self,path,data=None,blob=None,duration=None):
        if path=='asset':
            self.uploads+=1;hash=hashlib.sha256(blob).hexdigest()
            id=hash[:32];self.assets[id]=blob
            return {'id':id,'hash':hash,'bytes':len(blob),'duration':duration}
        if path in {'save-board','publish-drop'}:
            rows=self.boards if path=='save-board' else self.drops
            id=data.get('id') or str(len(rows)+1).zfill(32)
            old=rows.get(id)
            if old and old['revision']!=data['revision']:raise ValueError('Version conflict')
            rows[id]=dict(data,id=id,revision=(old['revision'] if old else 0)+1,role='editor',members=[],archived=None)
            return copy.deepcopy(rows[id])
        if path.startswith('board/'):return copy.deepcopy(self.boards[path.split('/')[1]])
        if path.startswith('drop/'):return copy.deepcopy(self.drops[path.split('/')[1]])
        if path.startswith('audio/'):return self.assets[path.split('/')[-1]]
        raise AssertionError(path)

@unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg unavailable')
class SharingTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup);self.root=Path(folder.name);self.cloud=MemoryCloud();self.job=Job()
        self.a=self.profile('alice');self.b=self.profile('bob')
        source=self.root/'tone.wav';tone(source)
        self.one=self.a.library.import_file(source,'Victory','Meme','win','','')
        self.two=self.a.library.import_file(source,'Crash','Effect','racing','','')
        self.board=self.a.library.save_board('Game night',add=[self.one['id'],self.two['id']])
    def profile(self,name):
        lib=Library(self.root/name);s=Studio(lib,'/nonexistent',pro_access=lambda:None)
        self.addCleanup(s.jobs.close);self.addCleanup(s.models.close)
        s.sharing=Sharing(s,cloud=self.cloud);return s
    def publish(self,**body):return self.a.sharing.publish({'mode':'board','board_id':self.board,**body},self.job)
    def test_real_audio_roundtrip_and_second_pull_do_not_duplicate_library(self):
        # Byte-identical original sounds are deliberately deduplicated by the cloud.
        published=self.publish()
        imported=self.b.sharing.pull({'mode':'board','id':published['id']},self.job)
        before=len(self.b.library.items());again=self.b.sharing.pull({'mode':'board','id':published['id']},self.job)
        self.assertEqual(imported['board_id'],again['board_id']);self.assertEqual(len(self.b.library.items()),before)
        self.assertEqual(self.b.library.boards()[0]['title'],'Game night')
        self.assertTrue(self.b.library.path(self.b.library.boards()[0]['clips'][0]).is_file())
    def test_local_edits_are_protected_and_confirmed_pull_keeps_audio(self):
        published=self.publish();pulled=self.b.sharing.pull({'mode':'board','id':published['id']},self.job)
        self.b.library.save_board('Unsent title',pulled['board_id'])
        with self.assertRaises(SharingConflict):self.b.sharing.pull({'mode':'board','id':published['id']},self.job)
        count=len(self.b.library.items());self.b.sharing.pull({'mode':'board','id':published['id'],'overwrite':True},self.job)
        self.assertEqual(len(self.b.library.items()),count);self.assertEqual(self.b.library.boards()[0]['title'],'Game night')
    def test_push_reuses_shared_audio_and_rejects_stale_revision(self):
        published=self.publish();pulled=self.b.sharing.pull({'mode':'board','id':published['id']},self.job)
        before=self.cloud.uploads;self.b.library.save_board('Edited by Bob',pulled['board_id'])
        updated=self.b.sharing.publish({'mode':'board','board_id':pulled['board_id'],'cloud_id':published['id'],'revision':1},self.job)
        self.assertEqual(updated['revision'],2);self.assertEqual(self.cloud.uploads,before)
        with self.assertRaises(ValueError):self.a.sharing.publish({'mode':'board','board_id':self.board,'cloud_id':published['id'],'revision':1},self.job)
        with self.assertRaises(ValueError):self.a.sharing.publish({'mode':'board','board_id':self.board,'cloud_id':published['id'],'revision':2},self.job)
        count=len(self.a.library.items())
        self.a.sharing.pull({'mode':'board','id':published['id']},self.job)
        self.assertEqual(len(self.a.library.items()),count)
        self.assertEqual(self.a.library.boards()[0]['title'],'Edited by Bob')
    def test_preview_does_not_import_and_bad_hash_is_rejected(self):
        published=self.publish();count=len(self.b.library.items());row=published['manifest'][0]
        result=self.b.sharing.preview({'mode':'board','id':published['id'],'asset_id':row['id']},self.job)
        self.assertEqual(len(self.b.library.items()),count);self.assertTrue(self.b.sharing.preview_path(row['hash']).is_file())
        self.b.sharing.preview_path(row['hash']).unlink();self.cloud.assets[row['id']]=b'tampered'
        with self.assertRaises(ValueError):self.b.sharing.preview({'mode':'board','id':published['id'],'asset_id':row['id']},self.job)
        self.assertTrue(result['preview_url'].startswith('/api/sharing/preview/'))
    def test_drop_subset_and_copy_are_separate_local_boards(self):
        result=self.a.sharing.publish({'mode':'drop','ids':[self.one['id']],'title':'Friday'},self.job)
        first=self.b.sharing.pull({'mode':'drop','id':result['id']},self.job)
        second=self.b.sharing.pull({'mode':'drop','id':result['id'],'new_copy':True},self.job)
        self.assertNotEqual(first['board_id'],second['board_id']);self.assertEqual(len(self.b.library.items()),1)
    def test_pro_gate_and_duration_validation_happen_before_upload(self):
        self.a.pro.require=Mock(side_effect=ValueError('Pro required'))
        with self.assertRaises(ValueError):self.publish()
        self.assertEqual(self.cloud.uploads,0)
        self.a.pro.require=lambda:None
        with self.a.library.db() as db:db.execute('UPDATE clips SET duration=121 WHERE id=?',(self.one['id'],))
        with self.assertRaises(ValueError):self.publish()
        self.assertEqual(self.cloud.uploads,0)
    def test_link_hosts_and_paths_are_restricted(self):
        id='a'*32
        self.assertEqual(parse_link(WEBSITE+'/shared/'+id),('board',id))
        self.assertEqual(parse_link(WEBSITE+'/drop/'+id),('drop',id))
        for value in ['http://127.0.0.1/private','https://evil.example/drop/'+id,WEBSITE+'/api/account/me','https://user:pass@'+WEBSITE.split('//')[1]+'/drop/'+id]:
            with self.assertRaises(ValueError):parse_link(value)
        with self.assertRaises(ValueError):Cloud(None).call('../account/me')
        with self.assertRaises(ValueError):self.b.sharing.preview_path('../private')


class CloudSafetyTests(unittest.TestCase):
    def response(self,value):
        stream=io.BytesIO(json.dumps(value).encode());return stream
    def test_public_drop_never_reads_or_transmits_account_token(self):
        account=Mock();opener=Mock();opener.open.return_value=self.response({'id':'a'*32})
        with patch('mimic.sharing.urllib.request.build_opener',return_value=opener):
            self.assertEqual(Cloud(account).call('drop/'+'a'*32)['id'],'a'*32)
        account._load_token.assert_not_called()
        request=opener.open.call_args.args[0]
        self.assertFalse(request.has_header('Authorization'))
        self.assertTrue(request.full_url.startswith(WEBSITE+'/api/share/drop/'))
    def test_private_board_requires_sign_in_and_rejects_arbitrary_paths(self):
        cloud=Cloud(None)
        for path in ['board/'+'a'*32,'https://evil.example/','../account/me','audio/board/private/file']:
            with self.assertRaises(ValueError):cloud.call(path)
    def test_oversized_response_cannot_be_imported(self):
        opener=Mock();opener.open.return_value=io.BytesIO(b'x'*(2*1024*1024+1))
        with patch('mimic.sharing.urllib.request.build_opener',return_value=opener):
            with self.assertRaises(ValueError):Cloud(None).call('audio/drop/'+'a'*32+'/'+'b'*32)
