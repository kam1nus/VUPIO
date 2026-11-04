"""Bounded min/max envelope from actual signed 16-bit PCM WAV frames."""
import wave
import numpy as np


def envelope(path, bins=480):
    with wave.open(str(path), 'rb') as source:
        frames = source.getnframes()
        rate = source.getframerate()
        channels = source.getnchannels()
        if not frames or not rate or source.getsampwidth() != 2 or not 1 <= channels <= 8:
            raise ValueError('Для волны нужен непустой PCM WAV')
        bins = min(max(1, int(bins)), 720, frames)
        pairs = []
        for i in range(bins):
            count = (i+1)*frames//bins-i*frames//bins
            samples = np.frombuffer(source.readframes(count), dtype='<i2')
            if len(samples) != count*channels:
                raise ValueError('Аудиофайл повреждён')
            pairs.append([round(int(samples.min())/32768, 4), round(int(samples.max())/32768, 4)])
    return {'duration': frames/rate, 'peaks': pairs}
