"""Update the main README only after both release installers are public."""
import base64
import json
import os
import re
import subprocess
import sys


def gh(*arguments):
    return json.loads(subprocess.check_output(['gh','api',*arguments]))


def updated_readme(text, build):
    match = re.search(r'^## Download VUPIO Alpha (\d+)\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    if not match or int(match[1]) >= build:
        return text
    section = re.sub(r'alpha-\d+', f'alpha-{build}', match[0])
    section = re.sub(r'(?<=Download VUPIO Alpha )\d+', str(build), section, count=1)
    return text[:match.start()] + section + text[match.end():]


def main():
    build = int(sys.argv[1])
    repository = os.environ['GITHUB_REPOSITORY']
    if repository != 'kam1nus/VUPIO' or not 1 <= build <= 999999999:
        raise SystemExit('Unexpected repository or build')
    release = gh(f'repos/{repository}/releases/tags/alpha-{build}')
    expected = {'VUPIO-macOS-AppleSilicon.pkg','VUPIO-Windows-x64-Setup.exe','SHA256SUMS.txt'}
    uploaded = {item['name'] for item in release['assets'] if item['state']=='uploaded' and item['size']>0}
    if release['draft'] or not expected.issubset(uploaded):
        raise SystemExit('Both tested installers must be public before linking the README')
    endpoint = f'repos/{repository}/contents/README.md'
    current = gh(endpoint + '?ref=main')
    text = base64.b64decode(current['content']).decode('utf-8')
    updated = updated_readme(text, build)
    if updated == text: return
    payload = dict(branch='main', message=f'Link verified VUPIO build {build} downloads',
                   sha=current['sha'], content=base64.b64encode(updated.encode()).decode())
    subprocess.run(['gh','api','--method','PUT',endpoint,'--input','-','--silent'],
                   input=json.dumps(payload).encode(),check=True)
    print(f'Linked verified build {build} in README')


if __name__ == '__main__': main()
