"""Fetch the pinned official Sparkle distribution and embed its framework."""
import hashlib
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tarfile
from urllib.request import urlopen

import certifi

VERSION = '2.10.1'
DIGEST = '1a856d2a9edb8e628de88121d7be04cf0e2167f8641650b78fca00b14244cf27'
root = Path(__file__).resolve().parents[1]
cache = root / 'build/dependencies/sparkle'
cache.mkdir(parents=True, exist_ok=True)
archive = cache / f'Sparkle-{VERSION}.tar.xz'
if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest() != DIGEST:
    temporary = archive.with_suffix('.partial')
    try:
        with urlopen(f'https://github.com/sparkle-project/Sparkle/releases/download/{VERSION}/{archive.name}',
                     context=ssl.create_default_context(cafile=certifi.where()), timeout=60) as response:
            with temporary.open('wb') as file:
                shutil.copyfileobj(response, file)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != DIGEST:
            raise ValueError('Sparkle distribution checksum mismatch')
        temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)
if not (cache / 'Sparkle.framework').is_dir():
    with tarfile.open(archive) as files:
        files.extractall(cache, filter='data')
destination = root / 'build/MIMIC.app/Contents/Frameworks/Sparkle.framework'
destination.parent.mkdir(parents=True, exist_ok=True)
if destination.exists():
    shutil.rmtree(destination)
subprocess.run(['/usr/bin/ditto', '--norsrc', '--noextattr', str(cache / 'Sparkle.framework'), str(destination)], check=True)
shutil.copyfile(cache / 'LICENSE', destination.parent.parent / 'Resources/Sparkle-LICENSE.txt')
