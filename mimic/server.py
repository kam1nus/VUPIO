import argparse
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import threading
import time
from collections import defaultdict
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .library import Library, select_fragment, suggest
from .sources import LicensedCatalog

ROOT = Path(__file__).resolve().parents[1]


class Audio:
    def __init__(self, executable):
        self.executable=str(executable)
        self.lock = threading.Lock()
        self.output_buffer=b''
        self.diagnostics=[]
        self.process = subprocess.Popen([str(executable), '--audio-helper'], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, bufsize=0)

    def command(self, op, **kwargs):
        with self.lock:
            if self.process.poll() is not None:
                raise ValueError('Аудиодвижок остановлен (код '+str(self.process.returncode)+'). Перезапустите звук в Settings → Аудиоустройства. '+' '.join(self.diagnostics)[-500:])
            self.process.stdin.write((json.dumps(dict(op=op, **kwargs))+'\n').encode())
            self.process.stdin.flush()
            # Helper emits exactly one JSON response per command; mic authorization is async in helper.
            import select
            deadline=time.monotonic()+8
            while True:
                if time.monotonic()>deadline:
                    self.process.kill();raise ValueError('Аудиоустройство не отвечает. Перезапустите звук в Settings и проверьте выход.')
                if b'\n' in self.output_buffer:
                    line,self.output_buffer=self.output_buffer.split(b'\n',1)
                    try:
                        result=json.loads(line)
                        if isinstance(result,dict):break
                    except (ValueError,UnicodeError):pass
                    self.diagnostics=(self.diagnostics+[line.decode(errors='replace')[:240]])[-8:]
                    continue
                if not select.select([self.process.stdout], [], [], max(0,deadline-time.monotonic()))[0]:
                    self.process.kill()
                    raise ValueError('Аудиоустройство не отвечает. Перезапустите звук в Settings и проверьте выход.')
                chunk=os.read(self.process.stdout.fileno(),65536)
                if not chunk:raise ValueError('Аудиодвижок завершился: '+str(self.process.poll())+'; '+' '.join(self.diagnostics))
                self.output_buffer+=chunk
                if len(self.output_buffer)>1024*1024:
                    self.process.kill();raise ValueError('Некорректный ответ аудиодвижка')
            if 'error' in result:
                raise ValueError(result['error'])
            return result

    def emergency_mute(self):
        if self.process.poll() is None:
            try:self.process.send_signal(signal.SIGUSR1)
            except ProcessLookupError:pass

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()


class App:
    def __init__(self, data, audio, host, port, tls=False):
        self.library = Library(data)
        self.audio = audio
        self.host, self.port, self.tls = host, port, tls
        self.admin_key = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.revision = 1
        self.preview_stop_epoch=0
        self.pair_code = None
        self.pair_until = 0
        self.attempts = defaultdict(list)
        self.started = time.time()
        self._studio=None
        with self.library.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS sessions (hash TEXT PRIMARY KEY, role TEXT, name TEXT, expiry REAL)')
        self.preferences_path=self.library.root/'preferences.json'
        try:
            self.preferences=json.loads(self.preferences_path.read_text())
        except (OSError, ValueError):
            self.preferences={}
        self.restore_audio_preferences()

    def restore_audio_preferences(self):
        # Store the device selection at launch without opening a duplex route.
        # A hung system device cannot take down Soundboard or Studio during startup.
        audio=self.audio
        if 'volume' in self.preferences:
            audio.command('volume',value=self.preferences['volume'])
        if self.preferences.get('outputUID'):
            matches=[d for d in audio.command('devices')['devices'] if d.get('uid')==self.preferences['outputUID']]
            if matches:
                try:
                    audio.command('output',device=matches[0]['id'],start=False)
                except ValueError:
                    pass
        if self.preferences.get('inputUID'):
            matches=[d for d in audio.command('devices').get('physicalInputs',[]) if d.get('uid')==self.preferences['inputUID']]
            if matches:
                try:audio.command('input',device=matches[0]['id'])
                except ValueError:pass
        if 'micGain' in self.preferences or 'polyphony' in self.preferences:
            audio.command('mixer',gain=float(self.preferences.get('micGain',.7)),polyphony=bool(self.preferences.get('polyphony',False)))
        virtual=next((d for d in audio.command('devices')['devices'] if d.get('uid')=='MIMICAudioDevice_UID'),None)
        if virtual and not self.preferences.get('manualAudioRouteV03'):
            try:audio.command('output',device=virtual['id'],start=False)
            except ValueError:pass

    def restart_audio(self):
        with self.lock:
            old=self.audio
            old.close()
            self.audio=type(old)(old.executable) if isinstance(old,Audio) else type(old)()
            self.restore_audio_preferences()
            self.preview_stop_epoch+=1
            return self.audio.command('status')

    def save_preference(self, **values):
        with self.lock:
            self.preferences.update(values)
            temporary=self.preferences_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.preferences))
            temporary.replace(self.preferences_path)

    def studio(self):
        with self.lock:
            if self._studio is None:
                from .studio import Studio
                self._studio=Studio(self.library,getattr(self.audio,'executable',ROOT/'build/MIMIC.app/Contents/MacOS/MIMIC'),self.changed)
            return self._studio

    def session(self, token):
        with self.library.db() as db:
            row = db.execute('SELECT * FROM sessions WHERE hash=? AND expiry>?',
                             (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        return dict(row) if row else None

    def issue(self, role, name):
        token = secrets.token_urlsafe(32)
        with self.library.db() as db:
            db.execute('INSERT INTO sessions VALUES (?,?,?,?)',
                       (hashlib.sha256(token.encode()).hexdigest(),role,name[:80],time.time()+30*86400))
        return token

    def changed(self):
        with self.lock:
            self.revision += 1


class Handler(BaseHTTPRequestHandler):
    server_version = 'MIMIC/0.3'
    def log_message(self, *_):
        pass  # Never log auth material or uploaded names.

    @property
    def app(self):
        return self.server.app

    def send(self, data, status=200, content='application/json; charset=utf-8', cookie=None):
        raw = json.dumps(data, ensure_ascii=False).encode() if content.startswith('application/json') else data
        self.send_response(status)
        self.send_header('Content-Type',content)
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header('Set-Cookie', 'mimic='+cookie+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000'+('; Secure' if self.app.tls else ''))
        self.end_headers()
        self.wfile.write(raw)

    def send_audio(self, path):
        """Serve authenticated PCM previews with range support for WebKit seeking."""
        with path.open('rb') as f:
            size=os.fstat(f.fileno()).st_size
            start,end=0,size-1
            value=self.headers.get('Range')
            if value:
                m=re.fullmatch(r'bytes=(\d*)-(\d*)',value)
                if m and (m[1] or m[2]):
                    if m[1]:start,end=int(m[1]),min(end,int(m[2])) if m[2] else end
                    else:start=max(0,size-int(m[2]))
                else:start=size
                if not 0<=start<=end<size:
                    self.send_response(416)
                    self.send_header('Content-Range',f'bytes */{size}')
                    self.send_header('Content-Length','0')
                    self.end_headers()
                    return
            self.send_response(206 if value else 200)
            self.send_header('Content-Type','audio/wav')
            self.send_header('Accept-Ranges','bytes')
            self.send_header('Content-Length',str(end-start+1))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            if value:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.end_headers()
            f.seek(start)
            left=end-start+1
            while left and (chunk:=f.read(min(left,65536))):
                self.wfile.write(chunk);left-=len(chunk)

    def body(self, maximum=64000):
        if self.headers.get('Transfer-Encoding'):
            raise ValueError('Chunked upload не поддерживается')
        length = int(self.headers.get('Content-Length','0'))
        if not 0 < length <= maximum:
            raise ValueError('Неверный размер запроса')
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError('Загрузка прервана')
        return raw

    def json_body(self):
        if self.headers.get_content_type() != 'application/json':
            raise ValueError('Ожидается JSON')
        return json.loads(self.body())

    def guard(self):
        self.connection.settimeout(30)
        # Bind to one explicitly selected private interface. Also reject public peer addresses.
        ip = ipaddress.ip_address(self.client_address[0])
        if not (ip.is_private or ip.is_loopback) or ip.is_unspecified:
            raise PermissionError('Только локальная сеть')
        host = self.headers.get('Host','')
        allowed = {f'{self.app.host}:{self.app.port}',f'127.0.0.1:{self.app.port}',f'localhost:{self.app.port}'}
        if host not in allowed:
            raise PermissionError('Недопустимый Host')
        origin = self.headers.get('Origin')
        expected = ('https' if self.app.tls else 'http')+'://'+host
        if origin and origin != expected:
            raise PermissionError('Запрос с другого сайта запрещён')
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise PermissionError('Запрос с другого сайта запрещён')
        cookie = SimpleCookie()
        cookie.load(self.headers.get('Cookie',''))
        self.session = self.app.session(cookie['mimic'].value) if 'mimic' in cookie else None
        self.local = ip.is_loopback

    def auth(self, admin=False):
        if not self.session or (admin and (self.session['role']!='admin' or not self.local)):
            raise PermissionError('Требуется вход на Mac' if admin else 'Сначала выполните спаривание')

    def do_GET(self):
        self.handle_request('GET')

    def do_POST(self):
        self.handle_request('POST')

    def handle_request(self, method):
        try:
            self.guard()
            path = urlsplit(self.path).path
            a = self.app
            if method == 'GET':
                static = {'/':'index.html','/app.js':'app.js','/style.css':'style.css',
                          '/aiweb.js':'aiweb.js','/studio.js':'studio.js','/settings.js':'settings.js','/discover.js':'discover.js',
                          '/manifest.webmanifest':'manifest.webmanifest','/sw.js':'sw.js','/icon.svg':'icon.svg',
                          '/apple-touch-icon.png':'apple-touch-icon.png',
                          '/vupio-icon-192.png':'vupio-icon-192.png','/vupio-icon-512.png':'vupio-icon-512.png'}
                if path in static:
                    file = ROOT/'web'/static[path]
                    types = {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8',
                             '.css':'text/css; charset=utf-8','.webmanifest':'application/manifest+json','.svg':'image/svg+xml','.png':'image/png'}
                    return self.send(file.read_bytes(),content=types[file.suffix])
                if path == '/api/health':
                    return self.send({'ok':True,'version':'0.4.3-unified'})
                self.auth()
                if path.startswith('/api/ai/'):
                    self.auth(True)
                    studio=a.studio()
                    if path=='/api/ai/status':return self.send(studio.status())
                    if path.startswith('/api/ai/job/'):
                        return self.send(studio.jobs.get(path.rsplit('/',1)[1]))
                    if path.startswith('/api/ai/analysis/'):
                        return self.send(studio.cached_analysis(path.rsplit('/',1)[1]) or {})
                    if path.startswith('/api/ai/source/'):
                        return self.send(studio.autofetch.editable_source(path.rsplit('/',1)[1]))
                    if path.startswith('/api/ai/wave/'):
                        from .waveform import envelope
                        _,_,_,_,kind,id=path.split('/')
                        if kind=='clip':file=a.library.path(id)
                        elif kind=='original':file=studio.original(id)
                        elif kind=='draft':_,file=studio.draft(id)
                        elif kind=='asset':_,file=studio.asset(id)
                        else:raise ValueError('Неизвестный источник волны')
                        return self.send(envelope(file))
                    if path.startswith('/api/ai/original/'):
                        return self.send_audio(studio.original(path.rsplit('/',1)[1]))
                    if path.startswith('/api/ai/asset/'):
                        _,file=studio.asset(path.rsplit('/',1)[1])
                        return self.send_audio(file)
                    if path.startswith('/api/ai/draft/'):
                        _,file=studio.draft(path.rsplit('/',1)[1])
                        return self.send_audio(file)
                    raise ValueError('Неизвестный адрес AI Studio')
                if path == '/api/state':
                    try:audio = a.audio.command('status')
                    except (ValueError,OSError) as error:
                        audio = {'running':False,'error':str(error),'volume':a.preferences.get('volume',.65),'activeClips':[]}

                    return self.send({'role':self.session['role'],'revision':a.revision,
                                      'items':a.library.items(),'audio':audio,'preview_stop_epoch':a.preview_stop_epoch})
                if path == '/api/remotes':
                    self.auth(True)
                    with a.library.db() as db:
                        rows=db.execute("SELECT hash,name,expiry FROM sessions WHERE role='remote' AND expiry>? ORDER BY expiry DESC",(time.time(),))
                        return self.send([{'id':r['hash'][:24],'name':r['name'],'expiry':r['expiry']} for r in rows])
                if path == '/api/settings':
                    self.auth(True)
                    devices=a.audio.command('devices')
                    return self.send({'devices':devices['devices'],'inputs':devices.get('inputs',[]),'physicalInputs':devices.get('physicalInputs',[]),
                                      'ffmpeg':bool(shutil.which('ffmpeg')), 'semantic_model':os.environ.get('MIMIC_EMBED_MODEL',''),
                                      'data_dir':str(a.library.root),'tls':a.tls,'bind':a.host,'port':a.port})
                if path == '/api/audio':
                    self.auth(True)
                    return self.send(a.audio.command('status'))
                if path == '/api/qr':
                    self.auth(True)
                    import qrcode
                    import qrcode.image.svg
                    import io
                    with a.lock:
                        if time.time()>a.pair_until:
                            raise ValueError('Код истёк. Создайте новый.')
                        # QR never contains secret. Enter the code displayed on Mac separately.
                        url = ('https' if a.tls else 'http')+'://'+os.environ.get('MIMIC_LAN_IP',a.host)+':'+str(a.port)
                    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage)
                    out = io.BytesIO(); img.save(out)
                    return self.send(out.getvalue(),content='image/svg+xml')
                if path.startswith('/api/file/'):
                    self.auth(True)
                    return self.send_audio(a.library.path(path.rsplit('/',1)[1]))
                raise ValueError('Неизвестный адрес')

            if path == '/api/login':
                body = self.json_body()
                if not self.local or not hmac.compare_digest(str(body.get('key','')), a.admin_key):
                    raise PermissionError('Вход доступен только на Mac с ключом запуска')
                return self.send({'ok':True},cookie=a.issue('admin','Mac'))
            if path == '/api/pair':
                body = self.json_body()
                with a.lock:
                    now = time.time()
                    for key in ['global',self.client_address[0]]:
                        a.attempts[key] = [t for t in a.attempts[key] if now-t < 60]
                        if len(a.attempts[key]) >= (20 if key=='global' else 5):
                            return self.send({'error':'Слишком много попыток. Подождите минуту.'},429)
                    for key in ['global',self.client_address[0]]:
                        a.attempts[key].append(now)
                    if now>a.pair_until or not a.pair_code or not hmac.compare_digest(str(body.get('code','')),a.pair_code):
                        raise PermissionError('Неверный или просроченный код')
                    a.pair_code = None
                    return self.send({'ok':True},cookie=a.issue('remote',str(body.get('name','iPhone'))))
            self.auth()
            if path == '/api/upload':
                self.auth(True)
                raw = self.body(100*1024*1024)
                tmp = a.library.root/(secrets.token_hex(16)+'.upload')
                try:
                    tmp.write_bytes(raw)
                    item = a.library.import_file(tmp,'Новый файл')
                finally:
                    tmp.unlink(missing_ok=True)
                a.changed()
                return self.send(item)
            body = self.json_body()
            if path == '/api/play':
                a.preview_stop_epoch+=1
                item = a.library.get(body['id'])
                result = a.audio.command('play',path=str(a.library.path(item['id'])),id=item['id'])
                return self.send(result)
            if path in ['/api/stop','/api/panic']:
                if path=='/api/panic' and hasattr(a.audio,'emergency_mute'):a.audio.emergency_mute()
                a.preview_stop_epoch+=1
                return self.send(a.audio.command('panic' if path.endswith('panic') else 'stop'))
            if path == '/api/volume':
                value = float(body['value'])
                if not 0 <= value <= 1:
                    raise ValueError('Громкость: 0–1')
                with a.lock:
                    try:
                        result = a.audio.command('volume', value=value)
                    except (ValueError, OSError):
                        # Local preview and the next mixer launch still use this setting.
                        result = {}
                    a.save_preference(volume=value)
                return self.send({**result, 'volume': value})
            if path == '/api/favorite':
                result = a.library.edit(body['id'],{'favorite':body['favorite']})
                a.changed(); return self.send(result)
            if path == '/api/search':
                return self.send(a.library.search(str(body.get('query',''))[:2000],bool(body.get('semantic'))))
            self.auth(True)
            if path.startswith('/api/ai/'):
                studio=a.studio()
                if path=='/api/ai/submit':return self.send(studio.submit(body))
                if path=='/api/ai/web-settings':return self.send(studio.finder.web.settings.save(body.get('tavily_key','')))
                if path=='/api/ai/cancel':
                    studio.jobs.cancel(body['job_id']);return self.send({'ok':True})
                if path=='/api/ai/discard':
                    studio.discard(body['draft_id']);return self.send({'ok':True})
                if path=='/api/ai/undo':
                    a.audio.command('stop');return self.send(studio.undo(body['draft_id']))
                if path=='/api/ai/unload':
                    studio.models.close();return self.send({'ok':True})
                raise ValueError('Неизвестная команда AI Studio')
            if path == '/api/pair/new':
                with a.lock:
                    a.pair_code = f'{secrets.randbelow(100000000):08d}'
                    a.pair_until = time.time()+120
                return self.send({'code':a.pair_code,'expires':a.pair_until,
                                  'url':('https' if a.tls else 'http')+'://'+os.environ.get('MIMIC_LAN_IP',a.host)+':'+str(a.port)})
            if path == '/api/remotes/revoke':
                id=str(body.get('id',''))
                if not re.fullmatch(r'[a-f0-9]{24}',id):raise ValueError('Неизвестный пульт')
                with a.library.db() as db:
                    db.execute("DELETE FROM sessions WHERE role='remote' AND substr(hash,1,24)=?",(id,))
                return self.send({'ok':True})
            if path == '/api/revoke':
                a.preview_stop_epoch+=1
                with a.library.db() as db:
                    db.execute("DELETE FROM sessions WHERE role='remote'")
                a.pair_code=None
                a.audio.command('panic')
                return self.send({'ok':True})
            if path == '/api/edit':
                result=a.library.edit(body['id'],body); a.changed(); return self.send(result)
            if path == '/api/delete':
                a.audio.command('stop')
                a.library.delete(body['id']); a.changed(); return self.send({'ok':True})
            if path == '/api/prepare':
                result=a.library.prepare(body); a.changed(); return self.send(result)
            if path == '/api/suggest':
                return self.send(suggest(str(body.get('text',''))[:4000]))
            if path == '/api/fragment':
                return self.send(select_fragment(body['query'], body.get('segments',[])))
            if path == '/api/sources':
                return self.send({'items':LicensedCatalog(a.library.root/'sources.json').search(str(body.get('query',''))[:500]),
                                  'mode':'Лицензированный пользовательский каталог; загрузка вручную'})
            if path == '/api/audio/restart':
                return self.send(a.restart_audio())
            if path == '/api/audio/input':
                result=a.audio.command('input',device=int(body['device']))
                a.save_preference(inputUID=result.get('inputUID',''))
                return self.send(result)
            if path == '/api/output':
                result=a.audio.command('output',device=int(body['device']))
                a.save_preference(outputUID=result.get('outputUID',''),manualAudioRouteV03=True)
                return self.send(result)
            if path == '/api/mixer':
                options={}
                for name in ['gain']:
                    if name in body:
                        value=float(body[name])
                        if not 0<=value<=1:raise ValueError('Уровень: 0–1')
                        options[name]=value
                for name in ['polyphony','monitor']:
                    if name in body:
                        if not isinstance(body[name],bool):raise ValueError('Ожидается переключатель')
                        options[name]=body[name]
                if 'monitorDevice' in body:options['monitorDevice']=int(body['monitorDevice'])
                result=a.audio.command('mixer',**options)
                preferences={}
                if 'gain' in options:preferences['micGain']=options['gain']
                if 'polyphony' in options:preferences['polyphony']=options['polyphony']
                if preferences:a.save_preference(**preferences)
                return self.send(result)
            if path == '/api/audio/probe':
                if not isinstance(body.get('enabled'),bool):raise ValueError('Ожидается переключатель')
                return self.send(a.audio.command('probe',enabled=body['enabled']))
            if path == '/api/audio/mic-test':
                options={'device':int(body.get('device',0)), 'gain':float(body.get('gain',.7))}
                if not 0<=options['gain']<=1:raise ValueError('Уровень голоса: 0–1')
                result=a.audio.command('mic_test',**options)
                if result.get('inputUID'):a.save_preference(inputUID=result['inputUID'],micGain=options['gain'])
                return self.send(result)
            if path == '/api/audio/mic-test-stop':
                return self.send(a.audio.command('mic_test_stop'))
            if path == '/api/audio/test':
                import wave,math,struct
                file=a.library.root/'mimic-diagnostic.wav'
                with wave.open(str(file),'wb') as wav:
                    wav.setparams((2,2,48000,0,'NONE','not compressed'))
                    wav.writeframes(b''.join(struct.pack('<hh',*[int(5000*math.sin(2*math.pi*523.25*n/48000)*min(1,n/480,(48000-n)/480))]*2) for n in range(48000)))
                return self.send(a.audio.command('play',path=str(file),id='MIMIC diagnostic tone'))
            if path == '/api/mic':
                if not isinstance(body.get('enabled'),bool):raise ValueError('Ожидается enabled: true/false')
                options={'enabled':body['enabled'],'gain':float(body.get('gain',.7))}
                if not 0<=options['gain']<=1:raise ValueError('Уровень голоса: 0–1')
                if body.get('device'):options['device']=int(body['device'])
                result=a.audio.command('mic',**options)
                if result.get('inputUID'):a.save_preference(inputUID=result['inputUID'],micGain=options['gain'])
                return self.send(result)
            raise ValueError('Неизвестная команда')
        except PermissionError as e:
            self.send({'error':str(e)},403)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            self.send({'error':str(e)[:2000]},400)


def detect_lan():
    if sys.platform=='win32':
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as route:
                route.connect(('192.0.2.1',9))  # Read Windows' selected local interface without sending traffic.
                address=ipaddress.ip_address(route.getsockname()[0])
                if address.is_private and not address.is_loopback and not address.is_unspecified:
                    return str(address)
        except OSError:
            pass
        return '127.0.0.1'
    for interface in ['en0','en1','en2']:
        try:
            value=subprocess.check_output(['/usr/sbin/ipconfig','getifaddr',interface],stderr=subprocess.DEVNULL,timeout=2).decode().strip()
            address=ipaddress.ip_address(value)
            if address.version==4 and address.is_private and not address.is_loopback:return value
        except (OSError,ValueError,subprocess.SubprocessError):pass
    return '127.0.0.1'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--audio', default=str(ROOT/'build/MIMIC.app/Contents/MacOS/MIMIC'))
    args=parser.parse_args()
    host=os.environ.get('MIMIC_BIND') or detect_lan()
    address=ipaddress.ip_address(host)
    if not address.is_private or address.is_unspecified or address.version!=4:
        raise SystemExit('MIMIC_BIND должен быть конкретным приватным IPv4 адресом (не 0.0.0.0)')
    port=int(os.environ.get('MIMIC_PORT','8765'))
    root=Path(os.environ.get('MIMIC_DATA',str(Path.home()/'Library/Application Support/MIMIC')))
    audio=Audio(args.audio)
    cert,key=os.environ.get('MIMIC_TLS_CERT'),os.environ.get('MIMIC_TLS_KEY')
    if bool(cert)!=bool(key):
        raise SystemExit('Укажите MIMIC_TLS_CERT и MIMIC_TLS_KEY вместе')
    app=App(root,audio,host,port,bool(cert))
    servers=[]
    runtime_written=False
    try:
        for bind in dict.fromkeys([host,'127.0.0.1']):
            server=ThreadingHTTPServer((bind,port),Handler)
            server.daemon_threads=True
            server.app=app
            if cert:
                context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.minimum_version=ssl.TLSVersion.TLSv1_2
                context.load_cert_chain(cert,key)
                server.socket=context.wrap_socket(server.socket,server_side=True)
            servers.append(server)
        scheme='https' if cert else 'http'
        url=f'{scheme}://127.0.0.1:{port}/#admin={app.admin_key}'
        runtime=root/'runtime.json'
        runtime.write_text(json.dumps({'url':url,'pid':os.getpid()})); runtime.chmod(0o600)
        runtime_written=True
        launch_file=os.environ.get('MIMIC_LAUNCH_FILE')
        if launch_file:
            # Native launcher owns this unique temporary file; no secret in logs is required.
            fd=os.open(launch_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as ready:
                json.dump({'url':url,'pid':os.getpid()},ready)
        print('MIMIC Mac: '+url,flush=True)
        print('LAN bind: '+host+' · data: '+str(root),flush=True)
        def stop(*_):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM,stop)
        signal.signal(signal.SIGINT,stop)
        for server in servers:
            threading.Thread(target=server.serve_forever,daemon=True).start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        app.audio.close()
        if app._studio is not None:app._studio.close()
        for server in servers:
            server.server_close()
        if runtime_written:(root/'runtime.json').unlink(missing_ok=True)


if __name__=='__main__':
    main()
