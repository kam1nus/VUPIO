"""Measurable audio features and heuristic onset candidates; not music understanding."""
import subprocess
import numpy as np
from .models import tool


def samples(path,channels,rate):
    p=subprocess.run([tool('ffmpeg'),'-v','error','-nostdin','-i',str(path),'-ac',str(channels),'-ar',str(rate),'-f','f32le','-'],capture_output=True,timeout=120)
    if p.returncode:raise ValueError(p.stderr.decode(errors='replace')[-1000:])
    return np.frombuffer(p.stdout,dtype='<f4')


def audible_edges(path):
    rate=16000
    stereo=samples(path,2,rate).reshape(-1,2)
    audible=np.any(np.abs(stereo)>=10**(-50/20),axis=1)
    if not audible.any():
        return None
    first=audible.argmax()/rate
    last=(len(audible)-audible[::-1].argmax())/rate
    return first,last


def analyze(path):
    x=samples(path,1,8000)
    actual_duration=len(x)/8000
    actual_rms=float(np.sqrt(np.mean(x*x))) if len(x) else 0
    actual_peak=float(np.max(np.abs(x))) if len(x) else 0
    if len(x)<80:return {'rms':actual_rms,'peak':actual_peak,'brightness_hz':0,'onsets':[],'duration':actual_duration}
    window=2000
    if len(x)<window:x=np.pad(x,(0,window-len(x)))
    frames=x[:len(x)//window*window].reshape(-1,window)
    energy=np.sqrt(np.mean(frames**2,axis=1)+1e-12)
    peak=actual_peak
    # Frequency centroid estimated on a bounded evenly spaced frame sample.
    chosen=frames[np.linspace(0,len(frames)-1,min(len(frames),100)).astype(int)]
    spectrum=np.abs(np.fft.rfft(chosen*np.hanning(window),axis=1))
    freqs=np.fft.rfftfreq(window,1/8000)
    centroid=float(np.mean((spectrum*freqs).sum(axis=1)/(spectrum.sum(axis=1)+1e-12)))
    delta=np.diff(energy,prepend=energy[0])
    order=np.argsort(delta)[::-1]
    onsets=[]
    for index in order:
        second=float(index*.25)
        if index<2 or second<.5 or delta[index]<.008:continue
        if all(abs(second-y['time'])>1.5 for y in onsets):onsets.append({'time':second,'strength':round(float(delta[index]),4)})
        if len(onsets)>=8:break
    return {'rms':round(actual_rms,5),'peak':round(peak,5),
            'brightness_hz':round(centroid),'onsets':onsets,'duration':round(actual_duration,3)}
