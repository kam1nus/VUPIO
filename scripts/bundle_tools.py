"""Copy and relocate Homebrew Mach-O executables, dependencies and ggml backends.
All rewritten dependencies must resolve inside Tools or Apple's system directories.
"""
import glob
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

DEST=Path(sys.argv[1]).resolve();DEST.mkdir(parents=True,exist_ok=True)
seen={};sources={}


def output(args):return subprocess.check_output(args,text=True)

def dependencies(path):
    lines=output(['otool','-L',str(path)]).splitlines()[1:]
    return [line.strip().split(' (compatibility')[0] for line in lines]


def rpaths(path):
    data=output(['otool','-l',str(path)])
    return re.findall(r'cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset',data)


def resolve(name,source):
    if name.startswith('/'):return Path(name)
    tail=Path(name).name
    candidates=[]
    if name.startswith('@loader_path/'):
        candidates.append(source.parent/name.removeprefix('@loader_path/'))
    for root in rpaths(source):
        root=root.replace('@loader_path',str(source.parent)).replace('@executable_path',str(source.parent))
        candidates.append(Path(root)/tail)
    candidates += [source.parent/tail,source.parent.parent/'lib'/tail]
    candidates += [Path(x) for x in glob.glob('/opt/homebrew/opt/*/lib/'+tail)]
    candidates += [Path(x) for x in glob.glob('/opt/homebrew/opt/*/libexec/'+tail)]
    for path in candidates:
        if path.exists():return path.resolve()
    raise RuntimeError('Unresolved dependency '+name+' from '+str(source))


def copy(source,name=None):
    source=Path(source).resolve();name=name or source.name
    if name in seen:
        if seen[name]!=source and source.read_bytes()!=seen[name].read_bytes():raise RuntimeError('Dependency collision: '+name)
        return DEST/name
    seen[name]=source
    target=DEST/name;shutil.copy2(source,target);target.chmod(0o755)
    sources[name]=str(source)
    deps=dependencies(source)
    # Remove the existing signature before rewriting load commands.
    subprocess.run(['codesign','--remove-signature',str(target)],capture_output=True)
    for dep in deps:
        if dep.startswith(('/usr/lib/','/System/')):continue
        resolved=resolve(dep,source)
        depname=Path(dep).name
        if resolved==source:continue
        copy(resolved,depname)
        subprocess.run(['install_name_tool','-change',dep,'@loader_path/'+depname,str(target)],check=True,capture_output=True)
    if target.suffix in ['.dylib','.so']:
        subprocess.run(['install_name_tool','-id','@loader_path/'+name,str(target)],check=True,capture_output=True)
    return target


release_models=os.environ.get('MIMIC_BUNDLE_MODELS')=='1'
for name in (['ffmpeg','ffprobe'] if release_models else ['ffmpeg','ffprobe','llama-server','whisper-cli']):
    found=shutil.which(name)
    if not found:raise SystemExit('Missing build dependency: '+name)
    copy(found,name)
if not release_models:
    for backend in glob.glob('/opt/homebrew/opt/ggml/libexec/*.so'):copy(backend)
for file in DEST.iterdir():
    if not file.is_file():continue
    for dep in dependencies(file):
        if dep.startswith(('/opt/','/usr/local/')):raise RuntimeError('Non-portable dependency: '+str(file)+' '+dep)
    subprocess.run(['codesign','--force','--sign','-',str(file)],check=True,capture_output=True)
import json
(DEST/'dependencies.json').write_text(json.dumps(sources,indent=2))
print('Bundled tools and libraries:',len(seen))
