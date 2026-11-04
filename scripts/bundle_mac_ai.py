"""Stage a relocatable llama server and compile a standalone CPU Whisper CLI."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mimic.net import download

LLAMA = ('https://github.com/ggml-org/llama.cpp/releases/download/b10917/llama-b10917-bin-macos-arm64.tar.gz',
         '3deb6ddac52ae7afa5768a10a26288214f2d635a4f7b13ceb96ddbb60ade993a')
WHISPER = ('https://codeload.github.com/ggml-org/whisper.cpp/tar.gz/refs/tags/v1.8.3',
           '870ba21409cdf66697dc4db15ebdb13bc67037d76c7cc63756c81471d8f1731a')


def unpack(asset, directory, name):
    url,digest=asset
    directory.mkdir(parents=True,exist_ok=True)
    archive=directory/(name+'.tar.gz')
    if not archive.exists():
        download(url,archive,maximum=48*1024*1024)
    with archive.open('rb') as file:
        if hashlib.file_digest(file,'sha256').hexdigest()!=digest:
            archive.unlink()
            raise ValueError('Unexpected archive checksum: '+name)
    output=directory/name
    output.mkdir(exist_ok=True)
    with tarfile.open(archive) as source:
        source.extractall(output,filter='data')
    return output


def bundle(tools, cache):
    staged=unpack(LLAMA,cache,'llama')/'llama-b10917'
    output=tools/'llama-server'
    output.mkdir(exist_ok=True)
    for file in staged.iterdir():
        if file.name=='llama-server' or file.suffix=='.dylib':
            shutil.copy2(file,output/file.name,follow_symlinks=False)
    license_url='https://raw.githubusercontent.com/ggml-org/llama.cpp/b10917/LICENSE'
    download(license_url,output/'LICENSE.txt',maximum=256*1024)

    staged=unpack(WHISPER,cache,'whisper')/'whisper.cpp-1.8.3'
    cmake=shutil.which('cmake') or str(Path(sys.executable).parent/'cmake')
    build=cache/'whisper-build'
    subprocess.run([cmake,'-S',str(staged),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release',
                    '-DCMAKE_OSX_ARCHITECTURES=arm64','-DBUILD_SHARED_LIBS=OFF','-DGGML_METAL=OFF',
                    '-DGGML_BLAS=OFF','-DGGML_OPENMP=OFF','-DGGML_NATIVE=OFF','-DWHISPER_BUILD_TESTS=OFF',
                    '-DWHISPER_BUILD_SERVER=OFF'],check=True)
    subprocess.run([cmake,'--build',str(build),'--target','whisper-cli','--parallel','6'],check=True)
    output=tools/'whisper-cli'
    output.mkdir(exist_ok=True)
    shutil.copy2(build/'bin/whisper-cli',output/'whisper-cli')
    shutil.copyfile(staged/'LICENSE',output/'LICENSE.txt')
    (tools/'ai-dependencies.json').write_text(json.dumps({'llama':LLAMA,'whisper':WHISPER},indent=2))


if __name__=='__main__':
    bundle(Path(sys.argv[1]),Path(sys.argv[2]))
