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
        self.device = options['device']
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
    def test_output_reorder_reopens_the_same_virtual_device(self):
        driver = Wasapi()
        audio = WindowsAudio(driver)
        self.addCleanup(audio.close)
        audio.ensure_output()
        original = audio.player
        devices = driver.query_devices()
        driver.query_devices = lambda: [devices[1], devices[0], *devices[2:]]
        audio.refresh()
        audio.ensure_output()
        self.assertFalse(original.active)
        self.assertEqual(audio.player.device, 0)
        self.assertEqual(audio.status()['outputUID'], 'MIMICAudioDevice_UID')
        self.assertTrue(audio.status()['virtualConnected'])

    def test_disconnected_virtual_output_does_not_send_voice_to_speakers(self):
        driver = Wasapi()
        audio = WindowsAudio(driver)
        self.addCleanup(audio.close)
        audio.command('mic', enabled=True, gain=1)
        original = audio.capture
        devices = driver.query_devices()
        driver.query_devices = lambda: [devices[0], *devices[2:]]
        audio.refresh()
        self.assertFalse(audio.status()['running'])
        with self.assertRaisesRegex(ValueError, 'selected audio output disconnected'):
            audio.ensure_output()
        self.assertFalse(original.active)
        self.assertFalse(audio.status()['mic'])
        self.assertFalse(audio.status()['virtualConnected'])
        driver.query_devices = lambda: devices
        audio.refresh()
        audio.ensure_output()
        self.assertTrue(audio.status()['virtualConnected'])
        self.assertFalse(audio.status()['mic'])

    def test_physical_input_keeps_its_identity_after_device_reorder(self):
        driver = Wasapi()
        audio = WindowsAudio(driver)
        self.addCleanup(audio.close)
        devices = driver.query_devices()
        driver.query_devices = lambda: [devices[3], *devices[:3]]
        audio.refresh()
        audio.command('mic', enabled=True)
        self.assertEqual(audio.capture.device, 0)
        self.assertEqual(audio.status()['inputUID'], 'wasapi:Physical mic')

    def test_devices_can_appear_after_an_empty_startup(self):
        driver = Wasapi()
        devices = driver.query_devices()
        driver.query_devices = lambda: []
        audio = WindowsAudio(driver)
        self.addCleanup(audio.close)
        driver.query_devices = lambda: devices
        audio.refresh()
        audio.ensure_output()
        self.assertTrue(audio.status()['virtualConnected'])

    def test_monitor_limiter_bounds_overlapping_clips(self):
        audio = WindowsAudio(Wasapi())
        self.addCleanup(audio.close)
        audio.ensure_output()
        tone = np.full((480, 2), 32767, dtype=np.int16)
        audio.clips = {str(index): (tone, 0) for index in range(8)}
        output = np.empty((480, 2), dtype=np.float32)
        audio.render(output, 480, None, None)
        audio.render_monitor(output, 480, None, None)
        self.assertTrue(np.isfinite(output).all())
        self.assertLessEqual(float(np.abs(output).max()), .981)

    def test_default_monitor_starts_with_playback_not_at_launch(self):
        audio=WindowsAudio(Wasapi());self.addCleanup(audio.close)
        self.assertTrue(audio.status()['monitor'])
        self.assertIsNone(audio.player);self.assertIsNone(audio.monitor)
        audio.command('mixer',monitor=True,monitorUID='',start=False)
        self.assertIsNone(audio.player)
        audio.ensure_output()
        self.assertTrue(audio.status()['monitorRunning'])
        self.assertEqual(audio.monitor_device,1)

    def test_physical_output_does_not_duplicate_local_audio(self):
        audio=WindowsAudio(Wasapi());self.addCleanup(audio.close)
        state=audio.command('output',device=1)
        self.assertTrue(state['running']);self.assertIsNone(audio.monitor)

    def test_saved_device_uid_survives_device_id_changes(self):
        class Reordered(Wasapi):
            def query_devices(self):
                rows=super().query_devices();return [rows[1],rows[0],*rows[2:]]
        audio=WindowsAudio(Reordered());self.addCleanup(audio.close)
        audio.command('mixer',monitor=True,monitorUID='wasapi:Speakers',start=False)
        self.assertIsNone(audio.monitor)
        audio.ensure_output()
        self.assertEqual(audio.monitor_device,2);self.assertTrue(audio.status()['monitorRunning'])

    def test_unavailable_monitor_does_not_break_virtual_output(self):
        audio=WindowsAudio(Wasapi());self.addCleanup(audio.close)
        audio.command('mixer',monitor=True,monitorUID='wasapi:Disconnected headphones',start=False)
        audio.ensure_output()
        self.assertTrue(audio.status()['virtualConnected']);self.assertFalse(audio.status()['monitorRunning'])
        self.assertIn('Reconnect',audio.status()['monitorNotice'])

    def test_monitor_failure_does_not_break_virtual_output(self):
        class FailedHeadphones(Wasapi):
            def OutputStream(self,**options):
                if options['device']==0:raise OSError('Disconnected')
                return Stream(**options)
        audio=WindowsAudio(FailedHeadphones());self.addCleanup(audio.close)
        audio.ensure_output()
        self.assertTrue(audio.status()['virtualConnected']);self.assertFalse(audio.status()['monitorRunning'])
        self.assertIn('Disconnected',audio.status()['monitorNotice'])

    def test_explicit_off_and_panic_then_next_play(self):
        audio=WindowsAudio(Wasapi());self.addCleanup(audio.close)
        audio.command('mixer',monitor=False,start=False);audio.ensure_output()
        self.assertIsNone(audio.monitor)
        audio.command('mixer',monitor=True,monitorDevice=1)
        self.assertEqual(audio.status()['monitorUID'],'wasapi:Speakers')
        audio.command('panic')
        self.assertIsNone(audio.monitor);self.assertFalse(audio.status()['mic'])
        audio.ensure_output()
        self.assertTrue(audio.status()['monitorRunning']);self.assertFalse(audio.status()['mic'])

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
            self.assertTrue(state['monitorRunning'])
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
