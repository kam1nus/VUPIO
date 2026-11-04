"""Sign inner Mach-O files first for a Developer ID release. No private keys in source."""
from pathlib import Path
import os,subprocess,sys
root=Path(sys.argv[1]);identity=os.environ.get('MIMIC_APP_SIGN_IDENTITY','-')
if identity=='-':raise SystemExit('Set MIMIC_APP_SIGN_IDENTITY to your Developer ID Application identity')
for f in sorted(root.rglob('*'),key=lambda p:len(p.parts),reverse=True):
 if not f.is_file() or f.is_symlink():continue
 with f.open('rb') as stream:magic=stream.read(4)
 if magic in [b'\xcf\xfa\xed\xfe',b'\xfe\xed\xfa\xcf',b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca']:
  args=['codesign','--force','--options','runtime','--timestamp','--sign',identity]
  if f==root/'Contents/MacOS/MIMIC':args+=['--entitlements',str(Path(__file__).resolve().parents[1]/'native/Release.entitlements')]
  subprocess.run(args+[str(f)],check=True)
