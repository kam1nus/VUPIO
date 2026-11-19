"""Opt-in HAL integration check. Emits test tones, records numeric meters only.

Run after scripts/build.sh. Physical capture is tested at zero gain, so the
microphone's audio is excluded from the virtual output and local monitoring.
"""
import math
from pathlib import Path
import sys
import tempfile
import time
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mimic.server import Audio, ROOT


audio = Audio(ROOT / 'build/MIMIC.app/Contents/MacOS/MIMIC')
try:
    audio.command('mixer', monitor=False, start=False)
    routes = audio.command('devices')['devices']
    routes = [route for route in routes if route['uid'] == 'MIMICAudioDevice_UID'
              or route['name'] == 'BlackHole 2ch']
    assert routes, 'Install MIMIC Microphone or BlackHole before this check.'
    with tempfile.TemporaryDirectory() as directory:
        files = []
        for rate, channels in [(44100, 1), (48000, 2)]:
            samples = (.3 * np.sin(2 * math.pi * 440 * np.arange(rate * 2) / rate) * 32767).astype('<i2')
            # Exercise a right-only file that the old probe reported as silence.
            pcm = samples if channels == 1 else np.column_stack([np.zeros_like(samples), samples])
            path = Path(directory) / f'tone-{rate}-{channels}.wav'
            with wave.open(str(path), 'wb') as output:
                output.setparams((channels, 2, rate, 0, 'NONE', 'not compressed'))
                output.writeframes(pcm.tobytes())
            files.append(path)
        for route in routes:
            print('Checking', route['name'], flush=True)
            state = audio.command('output', device=route['id'])
            assert state['running'], state
            for path in files:
                levels = []
                for volume in [.8, .2]:
                    audio.command('stop')
                    audio.command('probe', enabled=False)
                    audio.command('volume', value=volume)
                    audio.command('probe', enabled=True)
                    state = audio.command('play', path=str(path), id=path.name)
                    time.sleep(.4)
                    state = audio.command('status')
                    assert state['running'] and state['playing'] == path.name, state
                    assert state['probeUID'] == route['uid'], state
                    assert state['probeFrames'] > 0 and state['virtualMicLevel'] > .02, state
                    assert not state['mic'], state
                    levels.append(state['virtualMicLevel'])
                    stopped = audio.command('stop')
                    assert stopped['playing'] is None, stopped
                assert 2 < levels[0] / levels[1] < 6, levels
                print(path.name, 'received at both volumes', levels, flush=True)
            if audio.command('status')['micPermission'] == 3:
                state = audio.command('mic', enabled=True, gain=0)
                time.sleep(.4)
                state = audio.command('status')
                assert state['mic'] and state['captureHealthy'] and state['micConsumedFrames'] > 0, state
                # Reapplying the output rebuilds the graph and must resume requested capture.
                state = audio.command('output', device=route['id'])
                time.sleep(.3)
                state = audio.command('status')
                assert state['mic'] and state['running'] and state['captureHealthy'], state
                audio.command('mic', enabled=False)
                print('Physical capture and output reconfiguration passed at zero mic gain.', flush=True)
            else:
                print('Physical capture skipped: microphone permission is unavailable.', flush=True)
            state = audio.command('panic')
            assert not state['mic'] and not state['running'] and state['playing'] is None, state
        print('PASS: HAL inputs received resampled mono and right-only stereo clips, volume changes, STOP and PANIC.')
finally:
    audio.close()
