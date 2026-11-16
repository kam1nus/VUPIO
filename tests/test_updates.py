import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from mimic.updates import REPO, ReleaseRedirect, Updates, select_release

MODELS = 'a' * 64
BODY = b'new build archive'
DIGEST = hashlib.sha256(BODY).hexdigest()


def release(build, platform='macOS-AppleSilicon', extension='zip', models=MODELS, digest=DIGEST, draft=False):
    tag = f'alpha-{build}'
    full = platform + ('.pkg' if extension == 'zip' else '-Setup.exe')
    names = ['VUPIO-' + full, f'VUPIO-{platform}-Update-{models}.{extension}']
    return {'tag_name': tag, 'draft': draft, 'assets': [
        {'name': name, 'browser_download_url': f'{REPO}/releases/download/{tag}/{name}',
         'state': 'uploaded', 'size': len(BODY), 'digest': 'sha256:' + digest} for name in names]}


class UpdateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_uses_latest_public_compatible_release_and_keeps_full_fallback(self):
        old = release(4054)
        current = release(4055)
        draft = release(4056, draft=True)
        latest, full, update = select_release([old, draft, current], 'darwin', MODELS)
        self.assertEqual(latest, 4055)
        self.assertTrue(full.endswith('/VUPIO-macOS-AppleSilicon.pkg'))
        self.assertEqual(update['sha256'], DIGEST)
        self.assertEqual(update['size'], len(BODY))
        self.assertIsNone(select_release([current], 'darwin', 'b'*64)[2])
        self.assertIsNone(select_release([release(4055, digest='wrong')], 'darwin', MODELS)[2])
        self.assertEqual(select_release([release(4057, models='b'*64), old], 'darwin', MODELS)[0::2], (4057, None))

    def test_refuses_asset_and_redirect_from_another_host(self):
        current = release(4055)
        current['assets'][1]['browser_download_url'] = 'https://example.org/update.zip'
        self.assertIsNone(select_release([current], 'darwin', MODELS)[2])
        for url in ['https://example.org/file', 'http://github.com/file', 'https://github.com@evil.example/file']:
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, 'unexpected'):
                ReleaseRedirect({'github.com'}).redirect_request(None, None, 302, '', None, url)

    def wait_for(self, service, state):
        for _ in range(100):
            result = service.info()
            if result['state'] != 'downloading':
                break
            time.sleep(.02)
        self.assertEqual(result['state'], state, result)
        return result

    def prepare(self, platform='darwin'):
        service = Updates(self.root, 4054, platform)
        service.models_hash = MODELS
        build = release(4055) if platform == 'darwin' else release(4055, 'Windows-x64', 'exe')
        with patch('mimic.updates.open_release', return_value=io.BytesIO(json.dumps([build]).encode())):
            self.assertTrue(service.check()['app_update'])
        return service

    def test_background_download_verifies_and_reuses_cached_asset(self):
        service = self.prepare()
        with patch('mimic.updates.open_release', return_value=io.BytesIO(BODY)) as network:
            service.begin()
            self.wait_for(service, 'ready')
            network.assert_called_once()
        path = service.path(service.asset)
        self.assertEqual(path.read_bytes(), BODY)
        reopened = self.prepare()
        with patch('mimic.updates.open_release') as network:
            reopened.begin()
            self.wait_for(reopened, 'ready')
            network.assert_not_called()
        self.assertEqual(reopened.install(), {'platform':'macos'})
        request = json.loads((path.parent/'install.json').read_text())
        self.assertEqual(request, {'build':4055, 'sha256':DIGEST})

    def test_corruption_is_rejected_after_download_and_before_install(self):
        service = self.prepare()
        with patch('mimic.updates.open_release', return_value=io.BytesIO(b'X'*len(BODY))):
            service.begin()
            self.assertIn('integrity', self.wait_for(service, 'failed')['error'])
        self.assertEqual(list(service.root.iterdir()), [])
        with patch('mimic.updates.open_release', return_value=io.BytesIO(BODY)):
            service.begin()
            self.wait_for(service, 'ready')
        service.path(service.asset).write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'verification'):
            service.install()
        self.assertEqual(service.info()['state'], 'idle')

    def test_windows_opens_only_verified_exe(self):
        service = self.prepare('win32')
        with patch('mimic.updates.open_release', return_value=io.BytesIO(BODY)):
            service.begin()
            self.wait_for(service, 'ready')
        with patch('mimic.updates.os.startfile', create=True) as launch:
            self.assertEqual(service.install(), {'platform':'windows'})
            launch.assert_called_once_with(str(service.path(service.asset)), 'runas')
