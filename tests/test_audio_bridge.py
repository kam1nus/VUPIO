import tempfile,unittest,sys,json
from pathlib import Path
from mimic.server import Audio
class AudioBridgeTests(unittest.TestCase):
 def test_native_stdout_diagnostics_do_not_break_protocol(self):
  with tempfile.TemporaryDirectory() as tmp:
   f=Path(tmp)/'helper';f.write_text('#!'+sys.executable+'\nimport sys,json\nprint("HAL startup diagnostic",flush=True)\nfor line in sys.stdin:\n print("CoreAudio: format negotiation",flush=True)\n print(json.dumps({"op":json.loads(line)["op"],"mic":False}),flush=True)\n');f.chmod(0o755)
   audio=Audio(f)
   try:
    self.assertEqual(audio.command('status')['op'],'status')
    self.assertEqual(audio.command('mixer')['op'],'mixer')
    self.assertTrue(audio.diagnostics)
   finally:audio.close()
 def test_eof_is_a_clear_error(self):
  with tempfile.TemporaryDirectory() as tmp:
   f=Path(tmp)/'helper';f.write_text('#!/bin/sh\nexit 0\n');f.chmod(0o755)
   audio=Audio(f)
   try:
    with self.assertRaises(ValueError):audio.command('status')
   finally:audio.close()
