import tempfile
import sqlite3
from contextlib import closing
import unittest
from pathlib import Path
from mimic.library import Library

class BoardTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.library=Library(self.directory.name)
        with self.library.db() as db:
            for id in ('one','two','three'):
                (self.library.files/(id+'.wav')).write_bytes(b'fixture audio')
                db.execute('INSERT INTO clips(id,title,filename,favorite) VALUES (?,?,?,0)',(id,id,id+'.wav'))

    def test_shared_audio_and_legacy_order_survive_creation_rename_and_delete(self):
        before=self.library.items()
        first=self.library.save_board('Minecraft',add=['one','two','one'])
        second=self.library.save_board('Ranked',add=['two','three'])
        self.assertEqual(self.library.items(),before)
        self.library.save_board('Chill',first,add=['three'],remove=['one'])
        reloaded=Library(self.directory.name)
        self.assertEqual(reloaded.boards(),[{'id':first,'title':'Chill','clips':['two','three']},{'id':second,'title':'Ranked','clips':['two','three']}])
        reloaded.delete_board(first)
        self.assertEqual(len(reloaded.boards()),1)
        self.assertEqual(reloaded.items(),before)
        self.assertEqual(len(list(reloaded.files.glob('*.wav'))),3)

    def test_reordering_one_board_does_not_change_another_or_all_sounds(self):
        before=self.library.items()
        first=self.library.save_board('Game',add=['one','two','three'])
        second=self.library.save_board('Chill',add=['one','two','three'])
        self.library.swap_cards('one','three',first)
        self.assertEqual(self.library.boards()[0]['clips'],['three','two','one'])
        self.assertEqual(self.library.boards()[1]['clips'],['one','two','three'])
        self.assertEqual(self.library.items(),before)
        self.library.edit('one',{'favorite':True})
        with self.assertRaises(ValueError):self.library.swap_cards('one','three',first)
        with self.assertRaises(ValueError):self.library.swap_cards('one','missing',second)

    def test_delta_save_retains_members_added_while_picker_is_open(self):
        board=self.library.save_board('Game',add=['one'])
        self.library.board_members(board,add=['three'])
        self.library.save_board('Game night',board,add=['two'],remove=['one'])
        self.assertEqual(self.library.boards()[0]['clips'],['three','two'])

    def test_invalid_selection_is_atomic_and_cannot_create_empty_ghost_board(self):
        board=self.library.save_board('Game',add=['one'])
        for title,id,add,remove in [('Game',board,['two','missing'],['one']),('New',None,['missing'],[])]:
            with self.assertRaises(ValueError):self.library.save_board(title,id,add=add,remove=remove)
        self.assertEqual(self.library.boards(),[{'id':board,'title':'Game','clips':['one']}])
        for title in ('',' '*3,'x'*81,None):
            with self.assertRaises(ValueError):self.library.save_board(title)
        for selection in ('one',[None],{'one':True}):
            with self.assertRaises(ValueError):self.library.board_members(board,add=selection)

    def test_deleting_audio_cleans_every_board_and_removing_membership_keeps_audio(self):
        first=self.library.save_board('Game',add=['one','two'])
        self.library.save_board('Chill',add=['two'])
        self.library.board_members(first,remove=['one'])
        self.assertTrue(self.library.path('one').exists())
        self.library.delete('two')
        self.assertEqual([board['clips'] for board in self.library.boards()],[[],[]])
        self.assertEqual([item['id'] for item in self.library.items()],['three','one'])

    def test_opening_a_legacy_profile_adds_empty_boards_without_resetting_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'audio').mkdir();(root/'audio/saved.wav').write_bytes(b'original audio')
            with closing(sqlite3.connect(root/'library.sqlite3')) as db:
                db.execute('CREATE TABLE clips(id TEXT PRIMARY KEY,title TEXT,category TEXT,tags TEXT,description TEXT,favorite INTEGER,duration REAL,filename TEXT,license TEXT)')
                db.execute("INSERT INTO clips VALUES ('saved','Saved sound','Memes','test','Keep me',1,2.5,'saved.wav','User file')")
                db.execute('CREATE TABLE board_positions(id TEXT PRIMARY KEY,position INTEGER NOT NULL)')
                db.execute("INSERT INTO board_positions VALUES ('saved',42)")
                db.execute('CREATE TABLE vectors(key TEXT PRIMARY KEY,value TEXT)')
                db.execute("INSERT INTO vectors VALUES ('embedding','[1,2]')")
                db.commit()
            library=Library(root)
            self.assertEqual(library.boards(),[])
            self.assertEqual(library.items()[0]['title'],'Saved sound')
            self.assertEqual(library.items()[0]['favorite'],1)
            self.assertEqual(library.path('saved').read_bytes(),b'original audio')
            with library.db() as db:
                self.assertEqual(db.execute("SELECT position FROM board_positions WHERE id='saved'").fetchone()[0],42)
                self.assertEqual(db.execute("SELECT value FROM vectors WHERE key='embedding'").fetchone()[0],'[1,2]')
