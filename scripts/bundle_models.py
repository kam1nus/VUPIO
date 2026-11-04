"""Stage only the redistributable, digest-pinned release models."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mimic.models import MODELS, RELEASE_EMBEDDING
from mimic.net import download, parallel_download


class Progress:
    def check(self):
        pass
    def update(self, progress, message):
        pass


def valid(path, spec):
    if not path.is_file() or path.stat().st_size != spec['size']:
        return False
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest() == spec['sha256']


def bundle(destination, cache):
    destination.mkdir(parents=True,exist_ok=True)
    specs = [MODELS['language'], RELEASE_EMBEDDING, MODELS['speech']]
    notices = [
        ('https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/LICENSE','832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e'),
        ('https://huggingface.co/openmycel/Qwen3-Embedding-0.6B-GGUF/resolve/main/LICENSE','cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30'),
        ('https://raw.githubusercontent.com/openai/whisper/main/LICENSE','b5d65a59060e68c4ff940e1eddfa6f94b2d68fdf58ed7f4dd57721c997e35e9d'),
    ]

    def stage(spec, notice):
        name = spec['filename']
        target = destination/name
        if not valid(target,spec):
            temp = target.with_suffix('.part')
            try:
                cached = cache/name if cache else None
                if cached and valid(cached,spec):
                    shutil.copyfile(cached,temp)
                else:
                    url = spec.get('url') or f"https://huggingface.co/{spec['repo']}/resolve/main/{name}"
                    try:
                        parallel_download(url,temp,Progress(),spec['size'])
                    except (OSError,ValueError):
                        download(url,temp,Progress(),maximum=spec['size'])
                if not valid(temp,spec):
                    raise ValueError('Unexpected model digest: '+name)
                temp.replace(target)
            finally:
                temp.unlink(missing_ok=True)
        target.chmod(0o644)
        license_file=destination/(name+'.LICENSE.txt')
        url,digest=notice
        cached_notice=cache/license_file.name if cache else None
        if cached_notice and cached_notice.is_file() and hashlib.sha256(cached_notice.read_bytes()).hexdigest()==digest:
            shutil.copyfile(cached_notice,license_file)
        else:
            download(url,license_file,maximum=256*1024)
        if hashlib.sha256(license_file.read_bytes()).hexdigest()!=digest:
            raise ValueError('Unexpected license digest: '+name)
        print('Verified '+name,flush=True)

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(stage,specs,notices))
    (destination/'components.json').write_text(json.dumps(specs,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('destination',type=Path)
    parser.add_argument('--cache',type=Path)
    args=parser.parse_args()
    bundle(args.destination,args.cache)
