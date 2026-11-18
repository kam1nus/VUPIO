"""Rebuild and verify the signed Mac app using a lightweight release asset."""
import hashlib
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile

expected_build = int(sys.argv[1])
app, archive = (Path(value).resolve() for value in sys.argv[2:])
metadata = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
if int(metadata['CFBundleVersion']) != expected_build:
    raise SystemExit(f"Mac app build {metadata['CFBundleVersion']} does not match release {expected_build}.")
project = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='vupio-update-smoke-') as directory:
    root = Path(directory)
    previous = root / 'VUPIO.app'
    subprocess.run(['/bin/cp', '-cRP', app, previous], check=True)
    info = previous / 'Contents/Info.plist'
    metadata['CFBundleVersion'] = str(expected_build - 1)
    info.write_bytes(plistlib.dumps(metadata))
    cache = root / 'app-updates'
    cache.mkdir()
    with archive.open('rb') as compressed:
        digest = hashlib.file_digest(compressed, 'sha256').hexdigest()
    update = cache / f'vupio-{expected_build}-{digest}.zip'
    update.symlink_to(archive)
    (cache / 'install.json').write_text(f'{{"build":{expected_build},"sha256":"{digest}"}}')
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
let archive = URL(fileURLWithPath: CommandLine.arguments[3])
let request = LocalUpdate.PublicRequest(build: Int(CommandLine.arguments[4])!, sha256: CommandLine.arguments[5])
let appForInstaller = try LocalUpdate.stagePublic(archive: archive, request: request, installed: installed,
    stagingParent: installed.deletingLastPathComponent())
let package = try LocalUpdate.makeSystemInstaller(from: appForInstaller)
print(package.path)
''')
    subprocess.run([
        'swiftc', '-module-cache-path', str(root/'swift-cache'),
        str(main), str(project/'native/LocalUpdate.swift'), '-o', str(root/'verify'),
    ], check=True)
    output = subprocess.check_output(
        [root/'verify', previous, app, update, str(expected_build), digest], env={'MIMIC_DATA': directory}, text=True,
    )
    package = output.splitlines()[-1]
    paths = subprocess.check_output(['pkgutil', '--payload-files', package], text=True).splitlines()
    paths = [path.removeprefix('./').strip('/') for path in paths]
    app_path = 'Applications/VUPIO.app'
    directories_and_metadata = {'', '.', 'Applications', '._Applications', app_path, 'Applications/._VUPIO.app'}
    unexpected = [
        path for path in paths
        if path not in directories_and_metadata and not path.startswith(app_path + '/')
    ]
    if app_path + '/Contents/Info.plist' not in paths or unexpected:
        raise SystemExit(f'The system updater package must contain only VUPIO.app. Payload sample: {paths[:5]}, unexpected: {unexpected[:5]}.')
    print(output.splitlines()[0])
    print('The macOS installer contains only the application.')
