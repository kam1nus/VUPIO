"""Personal-test import of public audio. No license gate, cookies or executable page code.
HTTPS is connected to a validated pinned public IP; redirects are revalidated.
"""
import http.client,ipaddress,socket,ssl,time,re
from html.parser import HTMLParser
from urllib.parse import urlsplit,urljoin,quote
import certifi

EXTENSIONS=('.mp3','.wav','.ogg','.oga','.flac','.m4a','.aac','.opus','.aiff','.webm')

# These page URLs lead to players. The public-file loader has no adapter for them.
PLAYER_DOMAINS = ('youtube.com', 'youtu.be', 'tiktok.com', 'instagram.com',
                  'spotify.com', 'linkedin.com', 'soundcloud.com', 'music.apple.com')


def view_only(url):
    host = (urlsplit(url).hostname or '').removesuffix('.')
    return any(host == domain or host.endswith('.' + domain) for domain in PLAYER_DOMAINS)


def public_target(url):
    u=urlsplit(str(url))
    if len(url)>16384 or u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443):raise ValueError('Нужен публичный HTTPS-адрес без пароля и нестандартного порта')
    host=u.hostname.encode('idna').decode('ascii')
    records=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    ips=list(dict.fromkeys(r[4][0] for r in records))
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):raise ValueError('Загрузка из локальной/служебной сети запрещена')
    path=quote(u.path or '/',safe="/%:@!$&'()*+,;=-._~")
    if u.query:path+='?'+quote(u.query,safe="%=&/:?@!$'()*+,;~-._")
    return host,ips,path

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self,host,ip):
        super().__init__(host,443,timeout=20,context=ssl.create_default_context(cafile=certifi.where()));self.ip=ip
    def connect(self):
        raw=socket.create_connection((self.ip,443),timeout=self.timeout)
        try:self.sock=self._context.wrap_socket(raw,server_hostname=self.host)
        except Exception:raw.close();raise

class PublicResponse:
    def __init__(self,response,connection,url):self.response=response;self.connection=connection;self.url=url;self.headers=response.headers
    def read(self,n):return self.response.read(n)
    def __enter__(self):return self
    def __exit__(self,*args):self.response.close();self.connection.close()

def open_public(url,job=None):
    for _ in range(6):
        if job:job.check()
        host,ips,path=public_target(url);error=None
        for ip in ips[:3]:
            connection=PinnedHTTPS(host,ip)
            try:
                connection.request('GET',path,headers={'User-Agent':'MIMIC/0.4.3 (desktop personal soundboard)','Accept':'audio/*,text/html;q=0.9,*/*;q=0.5'})
                response=connection.getresponse();break
            except OSError as e:connection.close();error=e
        else:raise ValueError('Не удалось соединиться с сервером аудио: '+str(error))
        if response.status in {301,302,303,307,308}:
            location=response.getheader('Location');response.close();connection.close()
            if not location:raise ValueError('Пустое перенаправление источника')
            url=urljoin(url,location);continue
        if response.status<200 or response.status>=300:
            status=response.status;response.close();connection.close()
            raise ValueError('Источник вернул HTTP '+str(status)+'. Возможно, файл недоступен или требует входа.')
        return PublicResponse(response,connection,url)
    raise ValueError('Слишком много перенаправлений источника')

class AudioPage(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.primary=[];self.audio=[];self.downloads=[];self.in_audio=False
    def handle_starttag(self,tag,attributes):
        a=dict(attributes)
        if tag=='meta' and a.get('property',a.get('name','')).lower() in {'og:audio','og:audio:url','og:audio:secure_url','twitter:player:stream'} and a.get('content'):self.primary.append(a['content'])
        if tag=='audio':
            self.in_audio=True
            if a.get('src'):self.audio.append(a['src'])
        if tag=='source' and self.in_audio and a.get('src'):self.audio.append(a['src'])
        if tag=='a' and a.get('href') and urlsplit(a['href']).path.lower().endswith(EXTENSIONS):self.downloads.append(a['href'])
    def handle_endtag(self,tag):
        if tag=='audio':self.in_audio=False
    def candidate(self,base):
        for candidates in [self.primary,self.audio,self.downloads]:
            urls=list(dict.fromkeys(urljoin(base,v.strip()) for v in candidates if v.strip()))
            if not urls:continue
            if len(urls)>1:raise ValueError('На странице несколько аудиофайлов. Откройте конкретную кнопку/запись, а не общий список.')
            return urls[0]
        raise ValueError('На странице не найден прямой публичный аудиофайл. Выберите карточку со звуком, вставьте ссылку на MP3 в Discover или добавьте скачанный файл через Soundboard.')

def resolve_public_audio(source,job=None):
    page=source.get('page_url','');result=dict(source)
    if view_only(page):
        raise ValueError('Эта ссылка открывает проигрыватель. Выберите отдельную звуковую страницу в Discover или добавьте файл с компьютера.')
    if job:job.update(.08,'Checking · ищем публичный аудиофайл (без проверки лицензии)')
    with open_public(page,job) as response:
        mime=response.headers.get_content_type()
        if mime.startswith('audio/') or urlsplit(response.url).path.lower().endswith(EXTENSIONS):audio=response.url
        else:
            raw=response.read(3*1024*1024+1)
            if len(raw)>3*1024*1024:raise ValueError('Страница источника слишком большая')
            parser=AudioPage();parser.feed(raw.decode(response.headers.get_content_charset() or 'utf-8',errors='replace'));audio=parser.candidate(response.url)
    # Validate now as well as when actually connecting/downloading.
    public_target(audio)
    result.update(download_url=audio,can_import=True,personal_import=True,rights_checked=False,
                  license=result.get('license') or 'Не проверена · личный тест',reason='Личный тест: проверка прав отключена, источник сохранён.')
    return result

def download_public(url,path,job=None,maximum=100*1024*1024):
    size=0;deadline=time.monotonic()+180
    try:
        with open_public(url,job) as response,open(path,'wb') as target:
            length=int(response.headers.get('Content-Length',0) or 0)
            if length>maximum:raise ValueError(f'Аудиофайл больше {maximum//1048576} МБ')
            while True:
                if job:job.check()
                if time.monotonic()>deadline:raise ValueError('Превышено время загрузки')
                data=response.read(128*1024)
                if not data:break
                size+=len(data)
                if size>maximum:raise ValueError(f'Аудиофайл больше {maximum//1048576} МБ')
                target.write(data)
                if job:job.update(.2+min(.25,size/max(1,length)*.25),f'Downloading · {size/1048576:.1f} МБ')
        if not size:raise ValueError('Источник вернул пустой файл')
        return size
    except Exception:path.unlink(missing_ok=True);raise
