"""Create an original synthesized sound for a safe first test."""
import math
import struct
import wave
from pathlib import Path

target=Path(__file__).resolve().parents[1]/'samples'
target.mkdir(exist_ok=True)
with wave.open(str(target/'MIMIC-check.wav'),'wb') as file:
    file.setparams((1,2,48000,0,'NONE','not compressed'))
    samples=[]
    for n in range(72000):
        t=n/48000
        frequency=[523.25,659.25,783.99][min(2,int(t/.5))]
        envelope=min(1,(t%.5)*50)*min(1,(.5-t%.5)*12)
        samples.append(int(6000*envelope*math.sin(2*math.pi*frequency*t)))
    file.writeframes(struct.pack('<'+'h'*len(samples),*samples))
print(target/'MIMIC-check.wav')
