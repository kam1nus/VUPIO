"""Pinned, verified model downloads and private bundled llama.cpp runtimes."""
import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.request import Request,urlopen
from .net import download,parallel_download

MODELS={
 'language':{'title':'Qwen 2.5 · 0.5B Q4','filename':'qwen2.5-0.5b-instruct-q4.gguf',
             'repo':'Qwen/Qwen2.5-0.5B-Instruct-GGUF','size':397807936,
             'url':'https://registry.ollama.ai/v2/library/qwen2.5/blobs/sha256:c5396e06af294bd101b30dce59131a76d2b773e76950acc870eda801d3ab0515',
             'sha256':'c5396e06af294bd101b30dce59131a76d2b773e76950acc870eda801d3ab0515',
             'license':'Apache-2.0','license_url':'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/blob/main/LICENSE'},
 'embedding':{'title':'EmbeddingGemma · 300M BF16','filename':'embeddinggemma-300M-BF16.gguf',
              'repo':'ggml-org/embeddinggemma-300M-GGUF','size':621867104,
              'url':'https://registry.ollama.ai/v2/library/embeddinggemma/blobs/sha256:0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515',
              'sha256':'0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515',
              'license':'Gemma Terms of Use','license_url':'https://ai.google.dev/gemma/terms'},
 'speech':{'title':'Whisper Base · multilingual Q5','filename':'ggml-base-q5_1.bin',
           'repo':'ggerganov/whisper.cpp','size':59707625,
           'sha256':'422f1ae452ade6f30a004d7e5c6a43195e4433bc370bf23fac9cc591f01a8898',
           'license':'MIT','license_url':'https://github.com/ggml-org/whisper.cpp/blob/master/LICENSE'}
}

RELEASE_EMBEDDING={
 'title':'Qwen3 Embedding · 0.6B Q4',
 'filename':'Qwen3-Embedding-0.6B-Q4_K_M.gguf',
 'repo':'openmycel/Qwen3-Embedding-0.6B-GGUF',
 'size':396474560,
 'sha256':'23d234bb57a42528a22a13e7beb8b57d8844b2b9cc741b4c27a8ff132abf0dfd',
 'license':'Apache-2.0',
 'license_url':'https://huggingface.co/openmycel/Qwen3-Embedding-0.6B-GGUF/blob/main/LICENSE',
 'pooling':'last',
}

def tool(name):
    folder=os.environ.get('MIMIC_TOOLS')
    if folder:
        executable=name+'.exe' if sys.platform=='win32' else name
        for candidate in (Path(folder)/executable,Path(folder)/name/executable):
            if candidate.is_file():return str(candidate)
    found=shutil.which(name)
    if not found:raise ValueError(f'The build is missing {name}. Install the full VUPIO build.')
    return found


class Models:
    def __init__(self,root):
        self.root=Path(root)/'models';self.root.mkdir(exist_ok=True)
        self.verified={}
        self.processes={};self.lock=threading.RLock()
        self.stopping=threading.Event()
        self.language_profile=self.root/'language-profile.json'
        self.embedding_path=None
    def spec(self,kind):
        if kind=='language' and self.language_profile.exists():
            try:return json.loads(self.language_profile.read_text())
            except (ValueError,OSError):pass
        if kind=='embedding' and self.model_file(RELEASE_EMBEDDING).is_file():
            return RELEASE_EMBEDDING
        return MODELS[kind]
    def model_file(self,spec):
        path=self.root/spec['filename']
        bundle=os.environ.get('MIMIC_BUNDLED_MODELS')
        if not path.is_file() and bundle and not spec.get('imported'):
            return Path(bundle)/spec['filename']
        return path
    def path(self,kind):
        if kind not in MODELS:raise ValueError('Unknown model')
        spec=self.spec(kind)
        path=self.model_file(spec)
        if not path.is_file() or path.stat().st_size!=spec['size']:
            raise ValueError('First download the model “'+spec['title']+'” in Settings → AI models.')
        fingerprint=(spec['sha256'],path.stat().st_size,path.stat().st_mtime_ns)
        if self.verified.get(kind)!=fingerprint:
            with open(path,'rb') as file:digest=hashlib.file_digest(file,'sha256').hexdigest()
            if digest!=spec['sha256']:raise ValueError('Model checksum mismatch. Download it again.')
            self.verified[kind]=fingerprint
        if kind=='embedding' and spec['filename']==MODELS['embedding']['filename']:
            if self.embedding_path is None:
                from .gguf_compat import convert_embedding
                compatible=self.root/'embeddinggemma-llama-compat-v1.gguf'
                receipt=compatible.with_suffix('.json')
                valid=False
                if compatible.exists() and receipt.exists():
                    try:
                        record=json.loads(receipt.read_text())
                        with open(compatible,'rb') as file:valid=hashlib.file_digest(file,'sha256').hexdigest()==record['sha256'] and record['source_sha256']==spec['sha256']
                    except (ValueError,KeyError,OSError):pass
                if not valid:
                    convert_embedding(path,compatible)
                    with open(compatible,'rb') as file:digest=hashlib.file_digest(file,'sha256').hexdigest()
                    receipt.write_text(json.dumps({'source_sha256':spec['sha256'],'sha256':digest,'conversion':'gguf_compat.v1, tensor bytes unchanged'}))
                self.embedding_path=compatible
            return self.embedding_path
        return path
    def snapshot(self):
        result=[]
        for kind in MODELS:
            spec=self.spec(kind);path=self.model_file(spec)
            result.append(dict(spec,id=kind,installed=path.is_file() and path.stat().st_size==spec['size']))
        return result
    def import_language(self,source,title,job):
        source=Path(source)
        if not source.is_file() or not 1_000_000<source.stat().st_size<8_000_000_000:raise ValueError('Choose a GGUF model under 8 GB')
        with open(source,'rb') as file:
            if file.read(4)!=b'GGUF':raise ValueError('This is not a GGUF model')
            file.seek(0);job.update(.1,'Verifying local model…');digest=hashlib.file_digest(file,'sha256').hexdigest()
        filename='imported-language-'+digest[:16]+'.gguf';target=self.root/filename
        job.check()
        if not target.exists():
            try:os.link(source,target)
            except OSError:shutil.copyfile(source,target)
        profile={'title':str(title or source.stem)[:120],'filename':filename,'size':target.stat().st_size,
                 'sha256':digest,'license':'License of your selected model','license_url':'https://huggingface.co/docs/hub/repositories-licenses','imported':True}
        temporary=self.language_profile.with_suffix('.tmp');temporary.write_text(json.dumps(profile));temporary.replace(self.language_profile)
        self.verified.pop('language',None);self.close()
        return {'imported':True,'model':profile['title']}
    def install(self,kind,job):
        spec=self.spec(kind) if kind=='embedding' else MODELS[kind]
        target=self.root/spec['filename']
        if kind=='embedding' and self.model_file(spec)!=target:
            self.path(kind)
            return {'model':kind,'installed':True}
        if target.exists() and target.stat().st_size==spec['size']:
            with open(target,'rb') as f:valid=hashlib.file_digest(f,'sha256').hexdigest()==spec['sha256']
            if valid:
                if kind=='language':self.language_profile.unlink(missing_ok=True)
                self.verified.pop(kind,None)
                return {'model':kind,'installed':True}
        temporary=target.with_suffix('.part')
        try:
            parallel_download(spec.get('url') or 'https://huggingface.co/'+spec['repo']+'/resolve/main/'+spec['filename'],temporary,job,spec['size'])
            job.update(.97,'Checking SHA-256…')
            with open(temporary,'rb') as file:digest=hashlib.file_digest(file,'sha256').hexdigest()
            if digest!=spec['sha256']:raise ValueError('Model integrity check failed. Download it again.')
            job.check();temporary.replace(target)
            if kind=='language':self.language_profile.unlink(missing_ok=True);self.close()
            self.verified.pop(kind,None)
            return {'model':kind,'installed':True}
        finally:temporary.unlink(missing_ok=True)
    def _start(self,kind):
        with self.lock:
            self.stopping.clear()
            existing=self.processes.get(kind)
            fingerprint=self.spec(kind)['sha256']
            if existing and existing['process'].poll() is None and existing.get('fingerprint')==fingerprint:return existing
            if existing:
                old=existing['process']
                if old.poll() is None:
                    old.terminate()
                    try:old.wait(timeout=3)
                    except subprocess.TimeoutExpired:old.kill()
                existing['log'].close()
            path=self.path(kind)
            with socket.socket() as probe:
                probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
            token=secrets.token_urlsafe(32)
            bundled=os.environ.get('MIMIC_BUNDLED_MODELS')
            cpu_only=sys.platform=='win32' or (bundled and Path(bundled).is_dir())
            args=[tool('llama-server'),'-m',str(path),'--host','127.0.0.1','--port',str(port),
                  '--api-key',token,'-c','2048','-t','4','-ngl','0' if cpu_only else '99','--parallel','1','--no-webui']
            if cpu_only:args+=['--device','none','--no-kv-offload','--no-op-offload']
            if kind=='embedding':args+=['--embedding','--pooling',self.spec(kind).get('pooling','mean'),'-b','2048','-ub','2048']
            log=open(self.root/(kind+'-runtime.log'),'w')
            process=subprocess.Popen(args,stdout=log,stderr=log,stdin=subprocess.DEVNULL,
                                     env=dict(os.environ,GGML_METAL_LOG_LEVEL='1'))
            try:os.setpriority(os.PRIO_PROCESS,process.pid,10)
            except (OSError,AttributeError):pass
            runtime={'process':process,'url':f'http://127.0.0.1:{port}','token':token,'log':log,'fingerprint':fingerprint}
            self.processes[kind]=runtime
            until=time.monotonic()+90
            while time.monotonic()<until:
                if self.stopping.is_set():raise ValueError('AI engine stopped')
                if process.poll() is not None:
                    log.flush()
                    raise ValueError('Could not load the AI engine: '+(self.root/(kind+'-runtime.log')).read_text(errors='replace')[-1200:])
                try:
                    with urlopen(Request(runtime['url']+'/health',headers={'Authorization':'Bearer '+token}),timeout=1) as response:
                        if response.status==200:return runtime
                except Exception:time.sleep(.2)
            process.terminate();raise ValueError('Model startup timed out. Free some memory and try again.')
    def request(self,kind,endpoint,data):
        runtime=self._start(kind)
        req=Request(runtime['url']+endpoint,data=json.dumps(data).encode(),
                    headers={'Authorization':'Bearer '+runtime['token'],'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=120) as response:return json.load(response)
        except Exception as error:raise ValueError('The local model did not respond: '+str(error)) from error
    def embed(self,texts):
        result=self.request('embedding','/v1/embeddings',{'input':texts,'model':'local'})
        return [x['embedding'] for x in sorted(result['data'],key=lambda x:x['index'])]
    def generate(self,system,text,max_tokens=300):
        result=self.request('language','/v1/chat/completions',
                            {'messages':[{'role':'system','content':system},{'role':'user','content':text[:8000]}],
                             'temperature':0,'max_tokens':max_tokens,'chat_template_kwargs':{'enable_thinking':False},'response_format':{'type':'json_object'}})
        return json.loads(result['choices'][0]['message']['content'])
    def close(self):
        self.stopping.set()
        for runtime in list(self.processes.values()):
                p=runtime['process']
                if p.poll() is None:
                    p.terminate()
                    try:p.wait(timeout=3)
                    except subprocess.TimeoutExpired:p.kill()
                runtime['log'].close()
        self.processes.clear()
