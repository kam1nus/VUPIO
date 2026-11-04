"""Actual native C mixer, not a Python implementation of the mixer."""
import ctypes as C
import tempfile,subprocess,unittest,math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
class MixerDSPTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();lib=Path(cls.temp.name)/'mixer.dylib'
  subprocess.run(['clang','-std=c11','-O2','-shared',str(ROOT/'native/MixerDSP.c'),'-o',str(lib)],check=True)
  cls.lib=C.CDLL(str(lib));d=cls.lib;p=C.c_void_p;u=C.c_uint64;f=C.POINTER(C.c_float)
  specs={'mimic_mix_consumed_mic_frames':([p],u),'mimic_mix_meter':([p,C.c_int],C.c_float),'mimic_mix_create':([],p),'mimic_mix_destroy':([p],None),'mimic_voice_begin':([p,C.c_int],u),'mimic_voice_push':([p,C.c_int,u,f,f,C.c_uint],C.c_uint),'mimic_voice_end':([p,C.c_int,u],None),'mimic_voice_stop':([p,C.c_int],None),'mimic_mix_stop':([p,C.c_int],None),'mimic_mix_gains':([p,C.c_float,C.c_float],None),'mimic_mix_monitor':([p,C.c_int],None),'mimic_mix_render':([p,f,f,C.c_uint],None),'mimic_monitor_render':([p,f,f,C.c_uint],None),'mimic_voice_active':([p,C.c_int],C.c_int)}
  for name,(args,result) in specs.items():getattr(d,name).argtypes=args;getattr(d,name).restype=result
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def setUp(self):self.d=self.lib;self.m=self.d.mimic_mix_create();self.d.mimic_mix_gains(self.m,1,1)
 def tearDown(self):self.d.mimic_mix_destroy(self.m)
 def ptr(self,a):return a.ctypes.data_as(C.POINTER(C.c_float))
 def push(self,slot,a,ticket=None):
  a=np.array(a,dtype=np.float32);t=self.d.mimic_voice_begin(self.m,slot) if ticket is None else ticket
  written=self.d.mimic_voice_push(self.m,slot,t,self.ptr(a),self.ptr(a),len(a));return t,written
 def render(self,n,monitor=False):
  l=np.zeros(n,dtype=np.float32);r=l.copy();fn=self.d.mimic_monitor_render if monitor else self.d.mimic_mix_render;fn(self.m,self.ptr(l),self.ptr(r),n);np.testing.assert_array_equal(l,r);return l
 def test_voice_and_clip_sum(self):
  self.push(8,[.1]*512);self.push(0,[.2]*512);np.testing.assert_allclose(self.render(512),.3,atol=1e-6)
 def test_stop_clips_preserves_microphone(self):
  self.push(8,[.1]*512);self.push(0,[.4]*512);self.d.mimic_mix_stop(self.m,0);np.testing.assert_allclose(self.render(512),.1,atol=1e-6)
 def test_panic_silences_every_bus(self):
  self.push(8,[.1]*512);self.push(0,[.4]*512);self.d.mimic_mix_stop(self.m,1);np.testing.assert_array_equal(self.render(512),0)
 def test_independent_gain(self):
  self.push(8,[.2]*512);self.push(0,[.4]*512);self.d.mimic_mix_gains(self.m,.25,.5);np.testing.assert_allclose(self.render(512),.2,atol=1e-6)
 def test_eight_loud_clips_bounded_and_voice_remains(self):
  n=48000;t=np.arange(n)/48000
  tones=[.4*np.sin(2*np.pi*400*t) for _ in range(8)]+[.15*np.sin(2*np.pi*1000*t)]
  slots=list(range(8))+[8];tickets=[self.d.mimic_voice_begin(self.m,i) for i in slots];rendered=[]
  for start in range(0,n,512):
   count=min(512,n-start)
   for slot,ticket,tone in zip(slots,tickets,tones):self.push(slot,tone[start:start+count],ticket)
   rendered.append(self.render(count))
  out=np.concatenate(rendered)
  self.assertLessEqual(np.max(np.abs(out)),.981)
  spectrum=np.abs(np.fft.rfft(out))/n
  self.assertGreater(spectrum[1000],.01) # actual voice-frequency energy survives loud clips
  self.assertGreater(spectrum[400],.1)
 def test_stale_producer_cannot_write_reused_slot(self):
  old,_=self.push(0,[.4]*512);new,_=self.push(0,[.2]*512);_,n=self.push(0,[.9]*512,old);self.assertEqual(n,0);np.testing.assert_allclose(self.render(512),.2,atol=1e-6)
 def test_monitor_contains_clips_only(self):
  self.d.mimic_mix_monitor(self.m,1);self.push(8,[.1]*512);self.push(0,[.2]*512);self.render(512);np.testing.assert_allclose(self.render(512,True),.2,atol=1e-6)
 def test_end_of_file_drains_then_stops(self):
  t,_=self.push(0,[.2]*100);self.d.mimic_voice_end(self.m,0,t);out=self.render(512);self.assertEqual(self.d.mimic_voice_active(self.m,0),0);np.testing.assert_array_equal(out[100:],0)
 def test_stop_clears_monitor_tail(self):
  self.d.mimic_mix_monitor(self.m,1);self.push(0,[.2]*512);self.render(512);self.d.mimic_mix_stop(self.m,0);np.testing.assert_array_equal(self.render(512,True),0)
 def test_nonfinite_input_is_silence(self):
  self.push(0,[float('nan'),float('inf'),-float('inf')]);np.testing.assert_array_equal(self.render(3),0)
 def test_bounded_queue(self):
  _,written=self.push(0,np.zeros(100000));self.assertEqual(written,96000)

 def test_consumed_microphone_counts_only_available_frames(self):
  self.push(8,[.2]*100);self.render(512)
  self.assertEqual(self.d.mimic_mix_consumed_mic_frames(self.m),100)
  self.render(512);self.assertEqual(self.d.mimic_mix_consumed_mic_frames(self.m),100)
 def test_clip_cannot_light_microphone_bus_meter(self):
  self.push(0,[.2]*512);self.render(512)
  self.assertEqual(self.d.mimic_mix_meter(self.m,0),0)
  self.assertGreater(self.d.mimic_mix_meter(self.m,2),0)
  self.assertEqual(self.d.mimic_mix_consumed_mic_frames(self.m),0)
