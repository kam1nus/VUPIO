"""Rebuild and verify the signed Mac app using a lightweight release asset."""
import hashlib
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile

app, archive = (Path(value).resolve() for value in sys.argv[1:])
project = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='vupio-update-smoke-') as directory:
    root = Path(directory)
    previous = root / 'VUPIO.app'
    subprocess.run(['/bin/cp', '-cRP', app, previous], check=True)
    info = previous / 'Contents/Info.plist'
    metadata = plistlib.loads(info.read_bytes())
    build = int(metadata['CFBundleVersion'])
    metadata['CFBundleVersion'] = str(build - 1)
    info.write_bytes(plistlib.dumps(metadata))
    cache = root / 'app-updates'
    cache.mkdir()
    with archive.open('rb') as compressed:
        digest = hashlib.file_digest(compressed, 'sha256').hexdigest()
    (cache / f'vupio-{build}-{digest}.zip').symlink_to(archive)
    (cache / 'install.json').write_text(f'{{"build":{build},"sha256":"{digest}"}}')
    main = root / 'main.swift'
    main.write_text('''
import Foundation
let installed = URL(fileURLWithPath: CommandLine.arguments[1])
let complete = URL(fileURLWithPath: CommandLine.arguments[2])
let staged = try LocalUpdate.stagePublicRequest(installed: installed)
let actual = try LocalRelease.codeHash(of: staged)
let expected = try LocalRelease.codeHash(of: complete)
guard actual == expected else { fatalError("Rebuilt app has a different signature fingerprint.") }
try LocalUpdate.exchange(installed, staged)
guard LocalUpdate.version(of: installed) == LocalUpdate.version(of: complete) else {
    fatalError("Build number did not advance.")
}
print("Reused installed models, verified the original app signature and swapped the new app into place.")
''')
    subprocess.run(['swiftc', str(main), str(project/'native/LocalUpdate.swift'), '-o', str(root/'verify')], check=True)
    subprocess.run([root/'verify', previous, app], env={'MIMIC_DATA': directory}, check=True)
