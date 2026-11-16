"""Build the public updater's static index from the exact release assets."""
import hashlib
import json
from pathlib import Path
import re
import sys

tag, *files = sys.argv[1:]
if not re.fullmatch(r'alpha-[1-9][0-9]{0,8}', tag) or not files:
    raise SystemExit('Expected an Alpha tag and its installer files')
prefix = f'https://github.com/kam1nus/VUPIO/releases/download/{tag}/'
assets = []
for filename in files:
    path = Path(filename)
    with path.open('rb') as file:
        digest = hashlib.file_digest(file, 'sha256').hexdigest()
    assets.append({'name': path.name, 'state': 'uploaded', 'browser_download_url': prefix + path.name,
                   'size': path.stat().st_size, 'digest': 'sha256:' + digest})
print(json.dumps([{'tag_name': tag, 'draft': False, 'assets': assets}], indent=2))
