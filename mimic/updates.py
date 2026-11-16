"""Download platform updates from the official GitHub Releases channel."""
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

import certifi

REPO = 'https://github.com/kam1nus/VUPIO'
RELEASES = 'https://api.github.com/repos/kam1nus/VUPIO/releases?per_page=20'
ASSET_HOSTS = {'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
MAX_UPDATE = 1024 * 1024 * 1024
HASH = r'[0-9a-f]{64}'
PLATFORMS = {
    'darwin': ('macOS-AppleSilicon.pkg', 'macOS-AppleSilicon', 'zip'),
    'win32': ('Windows-x64-Setup.exe', 'Windows-x64', 'exe'),
}


def allowed_url(url, hosts):
    parts = urlsplit(url)
    return (parts.scheme == 'https' and parts.hostname in hosts and
            not parts.username and not parts.password and parts.port in (None, 443))


class ReleaseRedirect(HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_url(newurl, self.hosts):
            raise ValueError('GitHub returned an unexpected update download address.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_release(url, hosts, timeout):
    if not allowed_url(url, hosts):
        raise ValueError('Unexpected GitHub update address.')
    tls = ssl.create_default_context(cafile=certifi.where())
    opener = build_opener(HTTPSHandler(context=tls), ReleaseRedirect(hosts))
    return opener.open(Request(url, headers={'User-Agent': 'VUPIO-Updater'}), timeout=timeout)


def select_release(releases, platform, models_hash):
    if not isinstance(releases, list):
        raise ValueError('Invalid release response.')
    full_name, update_name, extension = PLATFORMS[platform]
    latest = 0
    full = update = None
    for release in releases:
        if not isinstance(release, dict) or release.get('draft') is not False:
            continue
        tag = release.get('tag_name')
        if not isinstance(tag, str) or not re.fullmatch(r'alpha-[1-9][0-9]{0,8}', tag):
            continue
        build = int(tag.removeprefix('alpha-'))
        if build <= latest:
            continue
        prefix = f'{REPO}/releases/download/{tag}/'
        assets = {
            asset['name']: asset for asset in release.get('assets', [])
            if isinstance(asset, dict) and isinstance(asset.get('name'), str)
            and asset.get('state') == 'uploaded'
            and asset.get('browser_download_url') == prefix + asset['name']
        }
        if 'VUPIO-' + full_name not in assets:
            continue
        latest = build
        full = prefix + 'VUPIO-' + full_name
        update = None
        if models_hash:
            name = f'VUPIO-{update_name}-Update-{models_hash}.{extension}'
            asset = assets.get(name) or {}
            size, digest = asset.get('size'), asset.get('digest')
            if type(size) is int and 0 < size <= MAX_UPDATE and isinstance(digest, str) and re.fullmatch('sha256:' + HASH, digest):
                update = {'build': build, 'url': prefix + name, 'size': size, 'sha256': digest[7:]}
    return latest, full, update


def bundled_model_hash():
    root = os.environ.get('MIMIC_BUNDLED_MODELS')
    if root:
        try:
            with (Path(root) / 'components.json').open('rb') as file:
                data = file.read(65537)
            if 0 < len(data) <= 65536:
                return hashlib.sha256(data).hexdigest()
        except OSError:
            pass
    return None


def sha256(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


class Updates:
    def __init__(self, root, installed, platform=sys.platform):
        self.installed = installed
        self.platform = platform
        self.root = Path(root) / 'app-updates'
        self.models_hash = bundled_model_hash() if getattr(sys, 'frozen', False) else None
        self.lock = threading.RLock()
        self.checked_at = None
        self.latest = 0
        self.full_url = None
        self.asset = None
        self.state = 'idle'
        self.received = 0
        self.error = ''
        self.installing = False
        try:
            for file in self.root.glob('vupio-*'):
                match = re.fullmatch(r'vupio-([0-9]+)-' + HASH + r'\.(zip|exe)', file.name)
                if match and int(match[1]) <= installed:
                    file.unlink(missing_ok=True)
        except OSError:
            pass

    def info(self):
        with self.lock:
            return {
                'installed': self.installed, 'latest': self.latest, 'download': self.full_url,
                'platform': self.platform, 'supported': self.models_hash is not None,
                'app_update': self.latest > self.installed and self.asset is not None,
                'size': self.asset['size'] if self.asset else 0,
                'received': self.received, 'state': self.state, 'error': self.error,
            }

    def check(self):
        with self.lock:
            if self.platform not in PLATFORMS:
                return self.info()
            if self.state == 'downloading' or self.installing or (
                    self.checked_at is not None and time.monotonic() - self.checked_at < 300):
                return self.info()
            try:
                with open_release(RELEASES, {'api.github.com'}, 8) as response:
                    raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError('Large release response.')
                releases = json.loads(raw)
                latest, full, asset = select_release(releases, self.platform, self.models_hash)
            except (OSError, ValueError, TypeError):
                raise ValueError('Could not check GitHub. Try again or open GitHub Releases.') from None
            if asset != self.asset:
                self.state = 'idle'
                self.received = 0
                self.error = ''
            self.latest, self.full_url, self.asset = latest, full, asset
            self.checked_at = time.monotonic()
            return self.info()

    def path(self, asset):
        extension = PLATFORMS[self.platform][2]
        return self.root / f'vupio-{asset["build"]}-{asset["sha256"]}.{extension}'

    @staticmethod
    def verified(file, asset):
        return file.is_file() and file.stat().st_size == asset['size'] and sha256(file) == asset['sha256']

    def begin(self):
        with self.lock:
            if self.state in {'downloading', 'ready'}:
                return self.info()
            asset = self.asset
            if not asset or asset['build'] <= self.installed:
                raise ValueError('No compatible app update. Check for updates first.')
            self.state, self.received, self.error = 'downloading', 0, ''
            try:
                threading.Thread(target=self.download, args=(asset,), daemon=True).start()
            except RuntimeError:
                self.state = 'idle'
                raise
            return self.info()

    def download(self, asset):
        target = self.path(asset)
        partial = None
        try:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            if not self.verified(target, asset):
                digest = hashlib.sha256()
                received = 0
                with tempfile.NamedTemporaryFile(dir=self.root, prefix='.partial-', delete=False) as file:
                    partial = Path(file.name)
                    with open_release(asset['url'], ASSET_HOSTS, 30) as stream:
                        while chunk := stream.read(256 * 1024):
                            received += len(chunk)
                            if received > asset['size']:
                                raise ValueError('Update size does not match GitHub.')
                            digest.update(chunk)
                            file.write(chunk)
                            with self.lock:
                                self.received = received
                if received != asset['size'] or digest.hexdigest() != asset['sha256']:
                    raise ValueError('Update integrity verification failed. Retry the download.')
                partial.replace(target)
            with self.lock:
                self.state, self.received = 'ready', asset['size']
        except Exception as error:
            with self.lock:
                self.state = 'failed'
                self.error = str(error) if isinstance(error, ValueError) else 'Update download failed. Check your connection and free disk space, then retry.'
        finally:
            if partial is not None:
                try:
                    partial.unlink(missing_ok=True)
                except OSError:
                    pass

    def install(self):
        with self.lock:
            asset = self.asset
            if self.state != 'ready' or self.installing or not asset or asset['build'] <= self.installed:
                raise ValueError('The update is not ready to install.')
            self.installing = True
        try:
            path = self.path(asset)
            if not self.verified(path, asset):
                with self.lock:
                    self.state, self.received = 'idle', 0
                raise ValueError('The saved update failed verification. Download it again.')
            if self.platform == 'win32':
                try:
                    os.startfile(str(path), 'runas')
                except OSError:
                    raise ValueError('The installer did not open. Confirm the Windows administrator prompt and try again.') from None
                return {'platform': 'windows'}
            # The native installer reads this request from the app's private cache,
            # rather than accepting a filesystem path from the browser.
            with tempfile.NamedTemporaryFile(dir=self.root, mode='w', prefix='.install-', delete=False) as ticket:
                request = Path(ticket.name)
                json.dump({'build': asset['build'], 'sha256': asset['sha256']}, ticket)
            try:
                request.replace(self.root / 'install.json')
            finally:
                request.unlink(missing_ok=True)
            return {'platform': 'macos'}
        finally:
            with self.lock:
                self.installing = False
