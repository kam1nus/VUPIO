"""Stage hash-pinned Windows x64 tools; keep the two ggml DLL sets separate."""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mimic.net import download

ASSETS = {
    'ffmpeg': ('GyanD/codexffmpeg','8.0.1','ffmpeg-8.0.1-essentials_build.zip',
               'e2aaeaa0fdbc397d4794828086424d4aaa2102cef1fb6874f6ffd29c0b88b673',
               ('ffmpeg.exe','ffprobe.exe'), 'https://ffmpeg.org/releases/ffmpeg-8.0.1.tar.xz'),
    'llama-server': ('ggml-org/llama.cpp','b10917','llama-b10917-bin-win-cpu-x64.zip',
                     'd36f855006035745a09c426e6c542a0907faaf2a300319a1cd395e494e7d69ee',
                     ('llama-server.exe',), 'https://github.com/ggml-org/llama.cpp/tree/b10917'),
    'whisper-cli': ('ggml-org/whisper.cpp','v1.8.3','whisper-bin-x64.zip',
                    'd824b1e37599f882b396e73f1ee0bfd5d0529f700314c48311dcbd00b803321d',
                    ('whisper-cli.exe',), 'https://github.com/ggml-org/whisper.cpp/tree/v1.8.3'),
}


def bundle(target):
    target.mkdir(parents=True,exist_ok=True)
    manifest = {}
    with tempfile.TemporaryDirectory() as tmp:
        for folder, (repo, version, name, digest, executables, source) in ASSETS.items():
            url = f'https://github.com/{repo}/releases/download/{version}/{name}'
            path = Path(tmp)/name
            download(url,path,maximum=350*1024*1024)
            with path.open('rb') as f:
                if hashlib.file_digest(f,'sha256').hexdigest() != digest:
                    raise ValueError('Archive digest mismatch: '+name)
            output = target/folder
            output.mkdir(exist_ok=True)
            with zipfile.ZipFile(path) as archive:
                found = {}
                for entry in archive.infolist():
                    filename = Path(entry.filename).name
                    if entry.is_dir() or not filename:
                        continue
                    if filename.lower() in executables or filename.lower().endswith('.dll'):
                        if filename in found:
                            raise ValueError('Ambiguous runtime file in '+name+': '+filename)
                        found[filename] = entry
                    elif filename.lower().startswith(('license','copying','readme','notice')):
                        found.setdefault(filename,entry)
                if not set(executables).issubset({n.lower() for n in found}):
                    raise ValueError('Missing tools in '+name)
                for filename, entry in found.items():
                    with archive.open(entry) as src, (output/filename).open('wb') as dst:
                        shutil.copyfileobj(src,dst)
            if folder != 'ffmpeg':
                download(f'https://raw.githubusercontent.com/{repo}/{version}/LICENSE',
                         output/'UPSTREAM-LICENSE.txt',maximum=256*1024)
            manifest[folder] = dict(version=version,source=source,archive=url,sha256=digest)
            print(f'Verified {name}',flush=True)
    (target/'dependencies.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')


if __name__ == '__main__':
    bundle(Path(sys.argv[1]))
