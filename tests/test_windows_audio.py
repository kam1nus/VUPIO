import tempfile
import unittest
from pathlib import Path
import wave

import numpy as np

from mimic.windows_audio import RATE, WindowsAudio


class Stream:
    def __init__(self, **options):
        self.active = False
        self.callback = options['callback']
    def start(self):
        self.active = True
    def abort(self):
        self.active = False
    def close(self):
        self.active = False


class Wasapi:
    PortAudioError = OSError
    WasapiSettings = dict
    OutputStream = Stream
    def __init__(self):
        self.capture_count = 0
    def InputStream(self, **options):
        self.capture_count += 1
        return Stream(**options)
    def query_hostapis(self):
        return [{'name':'Windows WASAPI','default_output_device':0}]
    def query_devices(self):
        return [{'name':name,'hostapi':0,'max_output_channels':outs,'max_input_channels':ins}
                for name, outs, ins in [('Speakers',2,0),('CABLE Input (VB-Audio)',2,0),
                                        ('CABLE Output (VB-Audio)',0,2),('Physical mic',0,1)]]


class WindowsAudioTests(unittest.TestCase):
    def test_virtual_route_plays_without_capture_and_monitor_excludes_voice(self):
        driver = Wasapi()
        audio = WindowsAudio(driver)
        self.addCleanup(audio.close)
        with tempfile.TemporaryDirectory() as root:
            file = Path(root)/'tone.wav'
            with wave.open(str(file),'wb') as f:
                f.setparams((2,2,RATE,0,'NONE','not compressed'))
                f.writeframes(np.full((960,2),16384,dtype='<i2').tobytes())
            state = audio.command('play',path=file,id='tone')
            self.assertEqual(state['activeClips'],['tone'])
            self.assertEqual(driver.capture_count,0)
            self.assertTrue(state['virtualConnected'])
            out = np.empty((480,2),dtype=np.float32)
            audio.command('mixer',monitor=True,monitorDevice=1)
            audio.command('mic',enabled=True,gain=1)
            audio.receive(np.full((480,1),.25,dtype=np.float32),480,None,None)
            audio.render(out,480,None,None)
            self.assertTrue(np.allclose(out,.325+.25))
            audio.render_monitor(out,480,None,None)
            self.assertTrue(np.allclose(out,.325))
            state = audio.command('panic')
            self.assertFalse(state['mic'])
            self.assertFalse(state['running'])
            self.assertEqual(state['activeClips'],[])
