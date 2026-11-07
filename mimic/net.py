"""HTTPS-only catalog downloads. No arbitrary URLs supplied by a remote client."""
import json
import ssl
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import certifi

AGENT='MIMIC/0.2 (local desktop audio library; https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia)'


def open_url(url, timeout=45):
    if urlsplit(url).scheme!='https':raise ValueError('Source must use HTTPS')
    context=ssl.create_default_context(cafile=certifi.where())
    return urlopen(Request(url,headers={'User-Agent':AGENT}),context=context,timeout=timeout)


def get_json(url):
    with open_url(url) as response:
        raw=response.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:raise ValueError('Catalog response is too large')
    return json.loads(raw)


def download(url,path,job=None,maximum=100*1024*1024,hosts=None):
    if hosts and urlsplit(url).hostname not in hosts:raise ValueError('Invalid download server')
    total=0
    with open_url(url,90) as response,open(path,'wb') as target:
        final=urlsplit(response.geturl())
        if final.scheme!='https':raise ValueError('Insecure redirect')
        if hosts and final.hostname not in hosts:raise ValueError('Unexpected download server')
        length=int(response.headers.get('Content-Length',0))
        if length>maximum:raise ValueError('File exceeds the size limit')
        while True:
            if job:job.check()
            chunk=response.read(256*1024)
            if not chunk:break
            total+=len(chunk)
            if total>maximum:raise ValueError('File exceeds the size limit')
            target.write(chunk)
            if job:job.update(min(.96,total/length) if length else .1,f'Downloaded {total/1048576:.1f} MB'+(f' / {length/1048576:.1f} MB' if length else ''))
    return total


def parallel_download(url,path,job,size,workers=6):
    """Bounded HTTP Range download, used only for fixed, hash-verified model weights."""
    import concurrent.futures
    import os
    import threading
    import time
    if not hasattr(os,'pwrite'):
        return download(url,path,job,maximum=size+1024)
    # Resolve the vendor's signed CDN URL once. Each range must explicitly be honored.
    context=ssl.create_default_context(cafile=certifi.where())
    with urlopen(Request(url,headers={'User-Agent':AGENT,'Range':'bytes=0-0'}),context=context,timeout=60) as response:
        if response.status!=206:
            return download(url,path,job,maximum=size+1024)
        resolved=response.geturl()
    if urlsplit(resolved).scheme!='https':raise ValueError('Insecure model server')
    fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_TRUNC,0o600)
    os.ftruncate(fd,size)
    lock=threading.Lock();progress={'bytes':0,'time':0};abort=threading.Event()
    block=4*1024*1024
    def fetch(start):
        end=min(size-1,start+block-1)
        req=Request(resolved,headers={'User-Agent':AGENT,'Range':f'bytes={start}-{end}'})
        for attempt in range(3):
            position=start
            try:
                with urlopen(req,context=context,timeout=90) as stream:
                    content_range=stream.headers.get('Content-Range','')
                    if stream.status!=206 or not content_range.startswith(f'bytes {start}-'):
                        raise ValueError('The server did not confirm the requested range')
                    while position<=end:
                        if abort.is_set():raise ValueError('Download cancelled')
                        job.check()
                        chunk=stream.read(min(128*1024,end-position+1))
                        if not chunk:raise ValueError('Range download interrupted')
                        os.pwrite(fd,chunk,position);position+=len(chunk)
                with lock:
                    progress['bytes']+=end-start+1
                    job.update(min(.96,progress['bytes']/size),f"Downloaded {progress['bytes']/1048576:.1f} / {size/1048576:.1f} MB")
                return
            except Exception:
                if attempt==2 or abort.is_set():raise
                job.check()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures=[pool.submit(fetch,start) for start in range(0,size,block)]
            try:
                for future in concurrent.futures.as_completed(futures):future.result()
            except Exception:
                abort.set()
                for future in futures:future.cancel()
                raise
    finally:os.close(fd)
    return size


def catalog_download(url,path,job=None,maximum=100*1024*1024):
    """Validate and pin every redirect, including when VPN DNS returns Fake-IP."""
    from .public_audio import download_public
    def allowed(host):
        return host=='upload.wikimedia.org' or host=='archive.org' or host.endswith('.archive.org')
    return download_public(url,path,job,maximum=maximum,hosts=allowed)
