"""Personal-test import of public audio. No license gate, cookies or executable page code.
HTTPS is connected to a validated pinned public IP; redirects are revalidated.
"""
import http.client,ipaddress,socket,ssl,time,re,json,threading
from html.parser import HTMLParser
from urllib.parse import urlsplit,urljoin,quote
import certifi
from . import BUILD

EXTENSIONS=('.mp3','.wav','.ogg','.oga','.flac','.m4a','.aac','.opus','.aiff','.webm')

# These page URLs lead to players. The public-file loader has no adapter for them.
PLAYER_DOMAINS = ('youtube.com', 'youtu.be', 'tiktok.com', 'instagram.com',
                  'spotify.com', 'linkedin.com', 'soundcloud.com', 'music.apple.com')

class PublicAudioError(ValueError):
    def __init__(self,message,code):super().__init__(message);self.code=code

_dns_cache={}
_dns_lock=threading.Lock()

def public_ip(value):
    address=ipaddress.ip_address(value)
    return address.is_global and not address.is_multicast and '%' not in str(address)

def vpn_fake_ip(value):
    address=ipaddress.ip_address(value)
    if address.version==6:
        if address in ipaddress.ip_network('2001:2::/48'):return True
        address=address.ipv4_mapped
    return address is not None and address.version==4 and address in ipaddress.ip_network('198.18.0.0/15')

def public_dns(host):
    """Fallback for VPN Fake-IP DNS, never permission to connect to a private IP.

    Bootstrap fixed public resolver IPs with verified TLS/SNI. Only the domain
    name is sent, never a media URL, query string, cookies or audio.
    """
    with _dns_lock:
        cached=_dns_cache.get(host)
        if cached and cached[0]>time.monotonic():return list(cached[1])
    for name,ip,path in [('cloudflare-dns.com','1.1.1.1','/dns-query'),
                         ('dns.google','8.8.8.8','/resolve')]:
        connection=PinnedHTTPS(name,ip,timeout=4)
        response=None
        try:
            connection.request('GET',path+'?name='+quote(host,safe='')+'&type=A',
                               headers={'Accept':'application/dns-json','User-Agent':f'VUPIO/{BUILD}'})
            response=connection.getresponse()
            if response.status!=200:continue
            raw=response.read(65537)
            if len(raw)>65536:continue
            payload=json.loads(raw)
            if not isinstance(payload,dict) or payload.get('Status')!=0:continue
            answers=payload.get('Answer',[])
            if not isinstance(answers,list):continue
            addresses=[];ttl=60
            for answer in answers[:32]:
                if not isinstance(answer,dict) or answer.get('type') not in (1,28):continue
                value=ipaddress.ip_address(answer['data'])
                if not public_ip(value):
                    raise PublicAudioError('The source resolves to a private or reserved address. Local network downloads remain blocked.','private_address')
                addresses.append(str(value))
                ttl=min(ttl,max(0,int(answer.get('TTL',0))))
            if addresses:
                addresses=list(dict.fromkeys(addresses))
                with _dns_lock:
                    if len(_dns_cache)>=128:_dns_cache.pop(next(iter(_dns_cache)))
                    _dns_cache[host]=(time.monotonic()+ttl,tuple(addresses))
                return addresses
        except PublicAudioError:raise
        except (OSError,ValueError,KeyError,TypeError,http.client.HTTPException):pass
        finally:
            if response:response.close()
            connection.close()
    raise PublicAudioError('Network DNS could not confirm a public address. Your VPN or DNS filter may be returning private Fake-IP addresses. Check the connection or use a VPN mode with real DNS addresses.','network_dns')


def view_only(url):
    host = (urlsplit(url).hostname or '').removesuffix('.')
    return any(host == domain or host.endswith('.' + domain) for domain in PLAYER_DOMAINS)


def public_target(url):
    u=urlsplit(str(url))
    if len(url)>16384 or u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443):raise ValueError('Use a public HTTPS URL without credentials or a custom port')
    host=u.hostname.encode('idna').decode('ascii')
    host=host.lower().rstrip('.')
    try:literal=ipaddress.ip_address(host)
    except ValueError:literal=None
    if literal is not None:
        if not public_ip(literal):raise PublicAudioError('Downloads from private or reserved networks are blocked. Choose a public website.','private_address')
        ips=[str(literal)]
    else:
        if '.' not in host or host.endswith(('.localhost','.local','.internal','.lan','.home','.test','.invalid')):
            raise PublicAudioError('Downloads from local network names are blocked. Choose a public website.','private_address')
        try:ips=list(dict.fromkeys(r[4][0] for r in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)))
        except socket.gaierror as error:
            if error.errno not in (socket.EAI_AGAIN,socket.EAI_FAIL):
                raise PublicAudioError('The source hostname could not be found. Check the URL and your network DNS.','network_dns') from error
            ips=[]
        if not ips:ips=public_dns(host)
        elif any(not public_ip(ip) for ip in ips):
            # A known benchmark address identifies Fake-IP DNS, including a
            # dual-stack response with a VPN-private IPv6 entry. Re-resolve the
            # hostname; never connect to any address from that private answer.
            # Ordinary private/sinkhole answers without Fake-IP remain blocked.
            if any(vpn_fake_ip(ip) for ip in ips):ips=public_dns(host)
            else:raise PublicAudioError('The source resolves to a private or reserved address. Check VPN/DNS settings; local-network downloads remain blocked.','private_address')
        # Recheck even cached/resolver-supplied results before pinning a socket.
        if not ips or any(not public_ip(ip) for ip in ips):
            raise PublicAudioError('The source has no verified public address. Local network downloads remain blocked.','private_address')
    path=quote(u.path or '/',safe="/%:@!$&'()*+,;=-._~")
    if u.query:path+='?'+quote(u.query,safe="%=&/:?@!$'()*+,;~-._")
    return host,ips,path

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self,host,ip,timeout=20):
        super().__init__(host,443,timeout=timeout,context=ssl.create_default_context(cafile=certifi.where()));self.ip=ip
    def connect(self):
        raw=socket.create_connection((self.ip,443),timeout=self.timeout)
        try:self.sock=self._context.wrap_socket(raw,server_hostname=self.host)
        except Exception:raw.close();raise

class PublicResponse:
    def __init__(self,response,connection,url):self.response=response;self.connection=connection;self.url=url;self.headers=response.headers
    def read(self,n):
        try:return self.response.read(n)
        except TimeoutError as error:raise PublicAudioError('Audio download timed out. Check your connection or VPN and try again.','network_timeout') from error
        except OSError as error:raise PublicAudioError('The audio connection was interrupted. Check your connection or VPN.','network_connect') from error
    def geturl(self):return self.url
    def __enter__(self):return self
    def __exit__(self,*args):self.response.close();self.connection.close()

def open_public(url,job=None,*,timeout=20,hosts=None):
    budget=getattr(job,'network_timeout',None)
    if isinstance(budget,(int,float)) and 0<budget<=20:timeout=min(timeout,budget)
    for _ in range(6):
        if job:job.check()
        if hosts:
            host=(urlsplit(url).hostname or '').lower().rstrip('.')
            if not (hosts(host) if callable(hosts) else host in hosts):raise ValueError('The server is outside the supported source')
        host,ips,path=public_target(url);error=None
        for ip in ips[:3]:
            connection=PinnedHTTPS(host,ip,timeout=timeout)
            try:
                connection.request('GET',path,headers={'User-Agent':f'VUPIO/{BUILD} (desktop soundboard)','Accept':'audio/*,text/html;q=0.9,*/*;q=0.5'})
                response=connection.getresponse();break
            except (OSError,http.client.HTTPException) as e:connection.close();error=e
        else:raise PublicAudioError('Could not connect to the audio server. Check your internet connection or VPN. '+str(error),'network_connect')
        if response.status in {301,302,303,307,308}:
            location=response.getheader('Location');response.close();connection.close()
            if not location:raise ValueError('Empty source redirect')
            url=urljoin(url,location);continue
        if response.status<200 or response.status>=300:
            status=response.status;response.close();connection.close()
            message={403:'The source denied this download (HTTP 403). Open the source in your browser or choose another public sound.',
                     429:'The source is limiting requests (HTTP 429). Wait before trying again.',
                     404:'The sound is no longer available (HTTP 404). Choose another result.'}.get(status,'Source returned HTTP '+str(status)+'. Try another source.')
            raise PublicAudioError(message,{403:'source_forbidden',429:'source_rate_limit',404:'source_missing'}.get(status,'source_http'))
        return PublicResponse(response,connection,url)
    raise ValueError('Too many source redirects')

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
            if len(urls)>1:raise ValueError('This page contains multiple audio files. Open an individual sound.')
            return urls[0]
        raise ValueError('No direct public audio file found. Choose a sound card, paste an MP3 URL in Discover or import a local file in Soundboard.')

def resolve_public_audio(source,job=None):
    page=source.get('page_url','');result=dict(source)
    if view_only(page):
        raise ValueError('This URL opens a player. Choose an individual sound page in Discover or import a local file.')
    if job:job.update(.08,'Checking · finding a public audio file')
    with open_public(page,job) as response:
        mime=response.headers.get_content_type()
        if mime.startswith('audio/') or urlsplit(response.url).path.lower().endswith(EXTENSIONS):audio=response.url
        else:
            raw=response.read(3*1024*1024+1)
            if len(raw)>3*1024*1024:raise ValueError('The source page is too large')
            parser=AudioPage();parser.feed(raw.decode(response.headers.get_content_charset() or 'utf-8',errors='replace'));audio=parser.candidate(response.url)
    # Validate now as well as when actually connecting/downloading.
    public_target(audio)
    result.update(download_url=audio,can_import=True,personal_import=True,rights_checked=False,
                  license=result.get('license') or 'Unverified · personal test',reason='Personal test import. Source metadata retained.')
    return result

def download_public(url,path,job=None,maximum=100*1024*1024,*,hosts=None):
    size=0;deadline=time.monotonic()+180
    try:
        options={'hosts':hosts} if hosts is not None else {}
        with open_public(url,job,**options) as response,open(path,'wb') as target:
            length=int(response.headers.get('Content-Length',0) or 0)
            if length>maximum:raise ValueError(f'Audio file exceeds {maximum//1048576} MB')
            while True:
                if job:job.check()
                if time.monotonic()>deadline:raise ValueError('Download timed out')
                data=response.read(128*1024)
                if not data:break
                size+=len(data)
                if size>maximum:raise ValueError(f'Audio file exceeds {maximum//1048576} MB')
                target.write(data)
                if job:job.update(.2+min(.25,size/max(1,length)*.25),f'Downloading · {size/1048576:.1f} MB')
        if not size:raise ValueError('Source returned an empty file')
        return size
    except Exception:path.unlink(missing_ok=True);raise
