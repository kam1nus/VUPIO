"""Create the appcast. Sign the resulting XML with Sparkle sign_update."""
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

build, filename, signature, models = sys.argv[1:]
if not re.fullmatch(r'[1-9][0-9]{0,8}', build):
    raise SystemExit('Invalid build number')
if not re.fullmatch(r'[A-Za-z0-9+/]{86}==', signature):
    raise SystemExit('Invalid Ed25519 signature')
if not re.fullmatch(r'[a-f0-9]{64}', models):
    raise SystemExit('Invalid model set hash')
path = Path(filename)
if path.name != 'VUPIO-macOS-AppleSilicon-Sparkle.zip':
    raise SystemExit('Unexpected Sparkle archive')
sparkle = 'http://www.andymatuschak.org/xml-namespaces/sparkle'
ET.register_namespace('sparkle', sparkle)
root = ET.Element('rss', version='2.0')
channel = ET.SubElement(root, 'channel')
ET.SubElement(channel, 'title').text = 'VUPIO updates'
ET.SubElement(channel, 'link').text = 'https://github.com/kam1nus/VUPIO/releases'
ET.SubElement(channel, 'description').text = 'Verified VUPIO application updates.'
item = ET.SubElement(channel, 'item')
ET.SubElement(item, 'title').text = f'VUPIO build {build}'
ET.SubElement(item, 'pubDate').text = format_datetime(datetime.now(timezone.utc))
ET.SubElement(item, f'{{{sparkle}}}minimumSystemVersion').text = '26.0'
ET.SubElement(item, 'enclosure', {
    'url': f'https://github.com/kam1nus/VUPIO/releases/download/alpha-{build}/{path.name}?models={models}',
    'length': str(path.stat().st_size),
    'type': 'application/octet-stream',
    f'{{{sparkle}}}version': build,
    f'{{{sparkle}}}shortVersionString': f'0.4.3 ({build})',
    f'{{{sparkle}}}edSignature': signature,
})
print(ET.tostring(root, encoding='unicode', xml_declaration=True))
