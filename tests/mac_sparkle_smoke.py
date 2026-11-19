"""Exercise signed Sparkle installation and relaunch in an isolated app bundle."""
import functools
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

project = Path(__file__).resolve().parents[1]
framework = project / 'build/dependencies/sparkle/Sparkle.framework'
signer = project / 'build/dependencies/sparkle/bin/sign_update'
key = os.environ['VUPIO_SPARKLE_PRIVATE_KEY'] if sys.argv[1] == '-' else Path(sys.argv[1]).read_text()
tamper = '--tamper' in sys.argv[2:]
public = (project / 'native/SparklePublicKey.txt').read_text().strip()


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True, stdout=subprocess.DEVNULL)


def sign(*args):
    return subprocess.run([str(signer), '--ed-key-file', '-', *map(str, args)],
                          input=key.encode(), check=True, stdout=subprocess.PIPE).stdout.decode().strip()


with tempfile.TemporaryDirectory(prefix='vupio-sparkle-') as directory:
    root = Path(directory)
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(SimpleHTTPRequestHandler, directory=directory))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}'
    source = root / 'main.swift'
    source.write_text('''
import Cocoa
let bundle = Bundle.main
let version = bundle.object(forInfoDictionaryKey:"CFBundleVersion") as! String
let data = URL(fileURLWithPath:bundle.object(forInfoDictionaryKey:"VUPIOTestData") as! String)
let model = try BundledModels.prepare(resources:bundle.resourceURL!,data:data)
guard try String(contentsOf:model.appendingPathComponent("test-model.bin"),encoding:.utf8) == "verified-model" else {
    fatalError("Model migration failed.")
}
if version == "999001" {
    try Data(version.utf8).write(to:data.appendingPathComponent("result"))
    exit(0)
}
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
var updater: AppUpdater!
updater = AppUpdater { info in
    print(info);fflush(stdout)
    if info["state"] as? String == "ready" { updater.install() }
    if info["state"] as? String == "failed" { exit(2) }
}
updater.automaticDownload = true
DispatchQueue.main.async { updater.check() }
app.run()
''')
    binary = root / 'updater-fixture'
    run('swiftc', source, project / 'native/AppUpdater.swift', project / 'native/BundledModels.swift',
        project / 'native/LocalUpdate.swift', '-module-cache-path', root / 'swift-cache',
        '-F', framework.parent, '-framework', 'Sparkle', '-framework', 'Cocoa',
        '-Xlinker', '-rpath', '-Xlinker', '@executable_path/../Frameworks', '-o', binary)
    fixture_id = 'test.vupio.updater.' + uuid.uuid4().hex
    data = root / 'data'
    data.mkdir()
    apps = []
    for build in ('999000', '999001'):
        app = root / build / 'VUPIO.app'
        contents = app / 'Contents'
        (contents / 'MacOS').mkdir(parents=True)
        (contents / 'Resources').mkdir()
        (contents / 'Frameworks').mkdir()
        shutil.copy2(binary, contents / 'MacOS/MIMIC')
        run('ditto', '--norsrc', '--noextattr', framework, contents / 'Frameworks/Sparkle.framework')
        models = [{'filename':'test-model.bin','sha256':hashlib.sha256(b'verified-model').hexdigest()}]
        manifest = json.dumps(models).encode()
        (contents / 'Resources/model-components.json').write_bytes(manifest)
        if build == '999000':
            embedded = contents / 'Resources/Models'
            embedded.mkdir()
            (embedded / 'components.json').write_bytes(manifest)
            (embedded / 'test-model.bin').write_bytes(b'verified-model')
        info = dict(CFBundleIdentifier=fixture_id, CFBundleExecutable='MIMIC',
                    CFBundleName='VUPIO', CFBundlePackageType='APPL', CFBundleVersion=build,
                    CFBundleShortVersionString='0.4.3', SUPublicEDKey=public,
                    SUFeedURL=url + '/appcast.xml', SUEnableAutomaticChecks=False,
                    SURequireSignedFeed=True, SUVerifyUpdateBeforeExtraction=True,
                    VUPIOTestData=str(data), LSUIElement=True,
                    NSAppTransportSecurity=dict(NSAllowsArbitraryLoads=True))
        (contents / 'Info.plist').write_bytes(plistlib.dumps(info))
        run('xattr', '-cr', app)
        run('codesign', '--force', '--deep', '--sign', '-', app)
        apps.append(app)
    archive = root / 'VUPIO-macOS-AppleSilicon-Sparkle.zip'
    run('ditto', '-c', '-k', '--keepParent', apps[1], archive)
    signature = sign('-p', archive)
    feed = subprocess.check_output([sys.executable, str(project/'scripts/write_sparkle_feed.py'),
                                    '999001', str(archive), signature, hashlib.sha256(manifest).hexdigest()], text=True)
    feed = feed.replace('https://github.com/kam1nus/VUPIO/releases/download/alpha-999001/', url + '/')
    (root / 'appcast.xml').write_text(feed)
    sign(root / 'appcast.xml')
    sign('--verify', root / 'appcast.xml')
    if tamper:
        contents = bytearray(archive.read_bytes())
        contents[128] ^= 1
        archive.write_bytes(contents)
    with (root / 'output.log').open('w+') as log:
        process = subprocess.Popen([str(apps[0]/'Contents/MacOS/MIMIC')], stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 80
            while time.monotonic() < deadline and not (data / 'result').exists():
                if process.poll() not in (None, 0):
                    break
                time.sleep(.25)
            if tamper:
                assert process.poll() == 2
                assert not (data / 'result').exists()
                installed = plistlib.loads((apps[0]/'Contents/Info.plist').read_bytes())
                assert installed['CFBundleVersion'] == '999000'
                run('codesign', '--verify', '--deep', '--strict', apps[0])
                print('PASS: real Sparkle rejected the altered archive and kept the previous signed app.')
            elif not (data / 'result').exists():
                log.seek(0)
                raise AssertionError(log.read()[-10000:])
            else:
                assert (data / 'result').read_text() == '999001'
                installed = plistlib.loads((apps[0]/'Contents/Info.plist').read_bytes())
                assert installed['CFBundleVersion'] == '999001'
                assert not (apps[0]/'Contents/Resources/Models').exists()
                run('codesign', '--verify', '--deep', '--strict', apps[0])
                print('PASS: signed feed and archive, real Sparkle app replacement, relaunch and reused external models.')
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
            server.shutdown()
