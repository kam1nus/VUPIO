"""Opt-in real BlackHole test. Does not open the physical microphone.
Run from project root: .venv/bin/python tests/native_smoke.py
It emits the bundled test tone to BlackHole 2ch and captures THAT virtual input.
Close Discord/other applications listening to BlackHole before running.
"""
import json
import math
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mimic.server import Audio, ROOT

audio=Audio(ROOT/'build/MIMIC.app/Contents/MacOS/MIMIC')
try:
    devices=audio.command('devices')['devices']
    blackhole=next(d for d in devices if d['name']=='BlackHole 2ch')
    print('Device:',blackhole)
    print('Output:',audio.command('output',device=blackhole['id']))
    if '--with-muted-mic' in sys.argv:
        mic=audio.command('mic',enabled=True,gain=0)
        assert mic.get('mic') is True and mic['micGain']==0,mic
        print('Physical microphone engine running at gain ZERO. Voice is neither emitted nor recorded.')
    with tempfile.TemporaryDirectory() as temp:
        captured=Path(temp)/'captured.wav'
        recorder=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-f','avfoundation',
                                   '-i',':BlackHole 2ch','-t','3','-ar','48000','-ac','2',
                                   '-c:a','pcm_s16le',str(captured)],stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        time.sleep(1)
        print('Play:',audio.command('play',path=str(ROOT/'samples/MIMIC-check.wav'),id='test'))
        time.sleep(.2)
        assert audio.command('status')['playing']=='test'
        out,err=recorder.communicate(timeout=15)
        if recorder.returncode:
            raise RuntimeError(err.decode())
        import array
        with wave.open(str(captured)) as file:
            samples=array.array('h',file.readframes(file.getnframes()))
        rms=math.sqrt(sum(x*x for x in samples)/len(samples))/32768
        print('Captured BlackHole RMS:',round(rms,5))
        assert rms>.005,'BlackHole received silence'
    assert audio.command('status')['playing'] is None
    assert audio.command('volume',value=.3)['volume']<.31
    audio.command('play',path=str(ROOT/'samples/MIMIC-check.wav'),id='stop-test')
    assert audio.command('stop')['playing'] is None
    panic=audio.command('panic')
    assert not panic['running'] and not panic['mic']
    print('PASS: output selection, real BlackHole signal, natural completion, volume, stop, panic')
finally:
    audio.close()
