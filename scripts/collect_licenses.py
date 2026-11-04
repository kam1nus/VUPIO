"""Collect third-party notices and exact local formula recipes for private builds."""
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import sys

resources=Path(sys.argv[1]);destination=resources/'ThirdPartyLicenses';destination.mkdir(exist_ok=True)
records=[]
for name in ['qrcode','numpy','certifi','pyinstaller']:
    dist=importlib.metadata.distribution(name)
    for entry in dist.files or []:
        if re.search(r'(^|/)(licen[sc]e[^/]*|copying[^/]*|notice[^/]*)$',str(entry),re.I):
            source=Path(dist.locate_file(entry))
            if source.is_file():
                target=destination/(name+'-'+source.name);shutil.copyfile(source,target)
    records.append({'component':name,'version':dist.version,'homepage':dist.metadata.get('Home-page','')})
source_map=json.loads((resources/'Tools/dependencies.json').read_text())
packages={}
for path in source_map.values():
    m=re.search(r'/Cellar/([^/]+)/([^/]+)/',path)
    if m:packages[m.group(1)]=m.group(2)
packages['python@3.14']='3.14.0'
for name,version in packages.items():
    root=Path('/opt/homebrew/Cellar')/name/version
    target=destination/name;target.mkdir(exist_ok=True)
    for file in root.rglob('*'):
        if file.is_file() and file.stat().st_size<2_000_000 and re.fullmatch(r'(license.*|licence.*|copying.*|copyright.*|notice.*)',file.name,re.I):
            shutil.copyfile(file,target/file.name)
    for formula in (root/'.brew').glob('*.rb'):
        shutil.copyfile(formula,target/formula.name)
    receipt=root/'INSTALL_RECEIPT.json'
    if receipt.exists():
        data=json.loads(receipt.read_text());records.append({'component':name,'version':version,'source':data.get('source',{}),'built_as_bottle':data.get('poured_from_bottle')})
(destination/'components.json').write_text(json.dumps(records,indent=2))
print('Collected notices/recipes:',len(records))
