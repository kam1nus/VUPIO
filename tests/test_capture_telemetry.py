"""Compile and exercise real Swift input telemetry. Synthetic PCM, no microphone."""
import unittest,subprocess,tempfile
from pathlib import Path
class CaptureTelemetryTests(unittest.TestCase):
 def test_native_meter_before_mixer_and_pcm_formats(self):
  root=Path(__file__).resolve().parents[1]
  with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
   exe=Path(d)/'meter'
   subprocess.run(['swiftc',str(root/'native/CoreInput.swift'),str(root/'tests/capture_telemetry.swift'),'-O','-module-cache-path',str(root/'build/swift-cache'),'-o',str(exe),'-framework','AVFoundation','-framework','CoreAudio'],check=True,capture_output=True,timeout=180)
   result=subprocess.run([str(exe)],check=True,capture_output=True,text=True,timeout=15)
   self.assertIn('PASS: raw physical telemetry without a running mixer',result.stdout)
