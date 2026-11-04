"""HTTPS-only catalog downloads. No arbitrary URLs supplied by a remote client."""
import json
import ssl
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import certifi

AGENT='MIMIC/0.2 (local desktop audio library; https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia)'


def open_url(url, timeout=45):
    if urlsplit(url).scheme!='https':raise ValueError('Источник должен использовать HTTPS')
    context=ssl.create_default_context(cafile=certifi.where())
    return urlopen(Request(url,headers={'User-Agent':AGENT}),context=context,timeout=timeout)


def get_json(url):
    with open_url(url) as response:
        raw=response.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:raise ValueError('Слишком большой ответ каталога')
    return json.loads(raw)


def download(url,path,job=None,maximum=100*1024*1024,hosts=None):
    if hosts and urlsplit(url).hostname not in hosts:raise ValueError('Недопустимый сервер загрузки')
    total=0
    with open_url(url,90) as response,open(path,'wb') as target:
        final=urlsplit(response.geturl())
        if final.scheme!='https':raise ValueError('Небезопасное перенаправление')
        if hosts and final.hostname not in hosts:raise ValueError('Неожиданный сервер загрузки')
        length=int(response.headers.get('Content-Length',0))
        if length>maximum:raise ValueError('Файл превышает допустимый размер')
        while True:
            if job:job.check()
            chunk=response.read(256*1024)
            if not chunk:break
            total+=len(chunk)
            if total>maximum:raise ValueError('Файл превышает допустимый размер')
            target.write(chunk)
            if job:job.update(min(.96,total/length) if length else .1,f'Загружено {total/1048576:.1f} МБ'+(f' / {length/1048576:.1f} МБ' if length else ''))
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
    if urlsplit(resolved).scheme!='https':raise ValueError('Небезопасный сервер модели')
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
                        raise ValueError('Сервер не подтвердил запрошенный диапазон')
                    while position<=end:
                        if abort.is_set():raise ValueError('Загрузка отменена')
                        job.check()
                        chunk=stream.read(min(128*1024,end-position+1))
                        if not chunk:raise ValueError('Загрузка диапазона прервана')
                        os.pwrite(fd,chunk,position);position+=len(chunk)
                with lock:
                    progress['bytes']+=end-start+1
                    job.update(min(.96,progress['bytes']/size),f"Загружено {progress['bytes']/1048576:.1f} / {size/1048576:.1f} МБ")
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
    """Restrict every redirect BEFORE requesting it; no arbitrary hosts or playlists."""
    import ipaddress,socket,time
    from urllib.request import build_opener,HTTPSHandler,HTTPRedirectHandler
    def validate(value):
        p=urlsplit(value);host=p.hostname or ''
        if p.scheme!='https' or p.username or p.password or p.port not in (None,443):raise ValueError('Недопустимый адрес аудио')
        if not (host=='upload.wikimedia.org' or host=='archive.org' or host.endswith('.archive.org')):raise ValueError('Сервер не входит в разрешённый каталог')
        addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError('Локальные сетевые адреса запрещены')
    class Redirect(HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            validate(newurl)
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    validate(url)
    opener=build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())),Redirect())
    total=0;deadline=time.monotonic()+180
    try:
        with opener.open(Request(url,headers={'User-Agent':AGENT}),timeout=25) as response,open(path,'wb') as target:
            length=int(response.headers.get('Content-Length',0))
            if length>maximum:raise ValueError('Файл больше 100 МБ')
            while True:
                if job:job.check()
                if time.monotonic()>deadline:raise ValueError('Превышено время загрузки')
                chunk=response.read(128*1024)
                if not chunk:break
                total+=len(chunk)
                if total>maximum:raise ValueError('Файл больше 100 МБ')
                target.write(chunk)
                if job:job.update(.2+min(.25,total/max(1,length)*.25),'Downloading · '+str(round(total/1048576,1))+' МБ')
        if not total:raise ValueError('Пустой файл')
        return total
    except Exception:
        path.unlink(missing_ok=True);raise
