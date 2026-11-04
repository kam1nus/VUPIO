import hashlib
import shutil
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np

from mimic.library import Library
from mimic.studio import Studio

class Job:
    def check(self):pass
    def update(self,*args):pass

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg not installed')
class StudioWaveTests(unittest.TestCase):
    def test_track_and_older_import_can_keep_full_recording_or_save_a_new_range(self):
        with tempfile.TemporaryDirectory() as data:
            lib=Library(data)
            studio=Studio(lib,'unused')
            self.addCleanup(studio.close)
            original=Path(data)/'track.wav'
            rate=8000
            t=np.arange(rate*40)/rate
            with wave.open(str(original),'wb') as f:
                f.setparams((1,2,rate,0,'NONE','not compressed'))
                f.writeframes((np.sin(t*2*np.pi*440)*np.where(t<24,1200,12000)).astype('<i2').tobytes())
            source={'source_id':'test:track','download_url':'https://example.org/audio.wav','title':'Track','description':'','personal_import':True}
            execute=studio.execute
            def analyze_or_execute(args,*other):
                return b'{"labels":[]}' if args[0]=='unused' else execute(args,*other)

            with patch.object(studio.finder,'resolve',return_value=source), \
                 patch.object(studio.finder,'saved',return_value={'query':'Найди трек'}), \
                 patch('mimic.public_audio.download_public',side_effect=lambda url,path,*args:shutil.copyfile(original,path)), \
                 patch.object(studio,'execute',side_effect=analyze_or_execute):
                track=studio.autofetch.prepare({'source_id':'test:track','add':False},Job())
                self.assertEqual(track['plan']['basis'],'full_track')
                self.assertAlmostEqual(track['report']['output']['duration'],40,delta=.03)
                short=studio.autofetch.prepare({'source_id':'test:track','category':'Meme'},Job())['item']
            self.assertAlmostEqual(short['duration'],8,delta=.1)

            # Simulate a card saved by a version that only recorded finder_imports.
            with lib.db() as db:
                db.execute('DELETE FROM finder_edits WHERE item=?',(short['id'],))
            recovered=studio.autofetch.editable_source(short['id'])
            self.assertEqual(recovered['report']['duration'],40)
            source_id=recovered['asset_id']
            whole=studio.plan({'asset_id':source_id,'command':'Оставь весь трек'},Job())['plan']
            self.assertEqual((whole['start'],whole['end']),(0,40))
            interval=studio.plan({'asset_id':source_id,'command':'Оставь 0:24–0:30'},Job())['plan']
            self.assertEqual((interval['start'],interval['end']),(24,30))
            moment=studio.plan({'asset_id':source_id,'command':'Подбери момент'},Job())['plan']
            self.assertLess(moment['start'],24)
            self.assertGreater(moment['end'],24)
            self.assertGreater(moment['start'],8)
            for plan,length in [(whole,40),(interval,6)]:
                cut=studio.autofetch.recut({'asset_id':source_id,**plan},Job())
                saved=studio.autofetch.commit(cut['asset_id'],Job(),{'variant':True})['item']
                self.assertAlmostEqual(saved['duration'],length,delta=.03)
                self.assertEqual(studio.autofetch.editable_source(saved['id'])['plan']['end'],plan['end'])
                self.assertTrue(studio.autofetch.commit(cut['asset_id'],Job(),{'variant':True})['duplicate'])
            self.assertEqual(len(lib.items()),3)

    def test_real_fades_apply_at_both_ends_of_trim_and_original_stays_intact(self):
        with tempfile.TemporaryDirectory() as data:
            p=Path(data)/'tone.wav';rate=48000
            t=np.arange(rate*3)/rate
            with wave.open(str(p),'wb') as f:
                f.setparams((1,2,rate,0,'NONE','not compressed'))
                f.writeframes((np.sin(t*2*np.pi*440)*12000).astype('<i2').tobytes())
            lib=Library(Path(data)/'library');item=lib.import_file(p,'Tone')
            original=lib.path(item['id']);before=hashlib.sha256(original.read_bytes()).digest()
            studio=Studio(lib,'unused')
            try:
                r=studio.render({'id':item['id'],'start':.5,'end':1.5,'fade_in':.3,'fade_out':.3},Job())
                _,path=studio.draft(r['draft_id'])
                with wave.open(str(path),'rb') as f:
                    self.assertAlmostEqual(f.getnframes()/f.getframerate(),1,delta=.015)
                    pcm=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype(float)
                level=lambda x:np.sqrt(np.mean(x*x))
                middle=level(pcm[40000:55000])
                self.assertLess(level(pcm[:4800]),.2*middle)
                self.assertLess(level(pcm[-4800:]),.2*middle)
                self.assertEqual(hashlib.sha256(original.read_bytes()).digest(),before)
                self.assertEqual(len(lib.items()),1)
            finally:studio.close()
