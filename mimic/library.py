import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.request import Request, urlopen


def run(args, timeout=180):
    p = subprocess.run(args, capture_output=True, timeout=timeout)
    if p.returncode:
        raise ValueError(p.stderr.decode(errors='replace')[-1800:])
    return p.stdout


class Library:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.files = self.root / 'audio'
        self.files.mkdir(exist_ok=True)
        with self.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS clips
                (id TEXT PRIMARY KEY, title TEXT, category TEXT, tags TEXT,
                 description TEXT, favorite INTEGER DEFAULT 0, duration REAL,
                 filename TEXT, license TEXT DEFAULT '')''')
            db.execute('CREATE TABLE IF NOT EXISTS vectors (key TEXT PRIMARY KEY, value TEXT)')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.root / 'library.sqlite3', timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def items(self):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM clips ORDER BY rowid DESC')]

    def get(self, id):
        with self.db() as db:
            row = db.execute('SELECT * FROM clips WHERE id=?', (id,)).fetchone()
        if not row:
            raise ValueError('File not found')
        return dict(row)

    def path(self, id):
        return self.files / self.get(id)['filename']

    def import_file(self, source, title, category='Memes', tags='', description='', license=''):
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            raise ValueError('Install FFmpeg: brew install ffmpeg')
        id = uuid.uuid4().hex
        target = self.files / (id + '.wav')
        try:
            # Decode only local uploaded files; deny network protocols and playlists.
            probe = json.loads(run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                                   '-show_format', '-of', 'json', str(source)], 30))
            try:duration = float(probe['format']['duration'])
            except (KeyError,TypeError,ValueError):raise ValueError('The audio file is empty or its duration cannot be determined')
            if not math.isfinite(duration) or not 0 < duration <= 1200:
                raise ValueError('Files up to 20 minutes are supported')
            run(['ffmpeg', '-v', 'error', '-nostdin', '-protocol_whitelist', 'file,pipe',
                 '-i', str(source), '-vn', '-t', '1200', '-ar', '48000', '-ac', '2',
                 '-c:a', 'pcm_s16le', str(target)])
            with self.db() as db:
                db.execute('INSERT INTO clips VALUES (?,?,?,?,?,?,?,?,?)',
                           (id, title[:160] or 'Untitled', category[:80] or 'Memes', tags[:500],
                            description[:4000], 0, duration, target.name, license[:16000]))
            return self.get(id)
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def edit(self, id, data):
        self.get(id)
        allowed = {'title':160, 'category':80, 'tags':500, 'description':4000, 'license':16000}
        with self.db() as db:
            for key, limit in allowed.items():
                if key in data:
                    db.execute(f'UPDATE clips SET {key}=? WHERE id=?', (str(data[key])[:limit], id))
            if 'favorite' in data:
                db.execute('UPDATE clips SET favorite=? WHERE id=?', (int(bool(data['favorite'])), id))
        return self.get(id)

    def delete(self, id):
        path = self.path(id)
        with self.db() as db:
            db.execute('DELETE FROM clips WHERE id=?', (id,))
        path.unlink(missing_ok=True)

    def prepare(self, data):
        item = self.get(data['id'])
        start, end = float(data.get('start', 0)), float(data.get('end', item['duration']))
        if not all(map(math.isfinite, [start, end])) or not 0 <= start < end <= item['duration'] + .05:
            raise ValueError('Check the start and end of the selection')
        filters = []
        if data.get('silence'):
            filters.append('silenceremove=start_periods=1:start_duration=0.08:start_threshold=-45dB:stop_periods=-1:stop_duration=0.25:stop_threshold=-45dB')
        if data.get('normalize'):
            filters.append('loudnorm=I=-16:TP=-1.5:LRA=11')
        temporary = self.root / (uuid.uuid4().hex + '.wav')
        try:
            args = ['ffmpeg', '-v', 'error', '-nostdin', '-ss', str(start), '-i', str(self.path(item['id'])), '-t', str(end-start)]
            if filters:
                args += ['-af', ','.join(filters)]
            run(args + ['-ar', '48000', '-ac', '2', str(temporary)])
            return self.import_file(temporary, data.get('title') or item['title'] + ' · cut',
                                    item['category'], data.get('tags', item['tags']),
                                    item['description'], item['license'])
        finally:
            temporary.unlink(missing_ok=True)

    def search(self, query, semantic=False):
        items = self.items()
        if not query.strip():
            return {'mode':'text', 'items':items}
        texts = [' '.join(str(i[k]) for k in ['title', 'category', 'tags', 'description']) for i in items]
        if semantic:
            model = os.environ.get('MIMIC_EMBED_MODEL')
            if not model:
                raise ValueError('Set MIMIC_EMBED_MODEL=embeddinggemma and start Ollama for the legacy semantic search.')
            def embed(text):
                key = model + ':' + text
                with self.db() as db:
                    row = db.execute('SELECT value FROM vectors WHERE key=?', (key,)).fetchone()
                if row:
                    return json.loads(row[0])
                req = Request('http://127.0.0.1:11434/api/embed',
                              data=json.dumps({'model':model, 'input':text}).encode(),
                              headers={'Content-Type':'application/json'})
                with urlopen(req, timeout=60) as response:
                    vec = json.load(response)['embeddings'][0]
                with self.db() as db:
                    db.execute('INSERT OR REPLACE INTO vectors VALUES (?,?)', (key, json.dumps(vec)))
                return vec
            q = embed(query)
            def cosine(v):
                denom = math.sqrt(sum(x*x for x in q)*sum(x*x for x in v))
                return sum(a*b for a,b in zip(q,v))/denom if denom else 0
            ranked = [(cosine(embed(t)), i) for t,i in zip(texts,items)]
            return {'mode':'ollama:'+model, 'items':[dict(i, score=round(s,3)) for s,i in sorted(ranked,key=lambda x:x[0],reverse=True)[:30]]}
        words = re.findall(r'\w+', query.lower())
        scored = [(sum(w in t.lower() for w in words), i) for t,i in zip(texts,items)]
        return {'mode':'text', 'items':[i for score,i in sorted(scored,key=lambda x:x[0],reverse=True) if score]}


def suggest(text):
    words = re.findall(r'[\w-]+', text.lower())
    stop = {'\u0434\u043b\u044f','\u044d\u0442\u043e','\u043a\u0430\u043a','\u0447\u0442\u043e','\u0438\u043b\u0438','the','and','with','\u0437\u0432\u0443\u043a','\u043c\u0435\u043c'}
    tags = list(dict.fromkeys(w for w in words if len(w)>2 and w not in stop))[:10]
    return {'title':' '.join(text.strip().split()[:8])[:100] or 'New clip', 'tags':', '.join(tags), 'mode':'Local description-based heuristic'}


def select_fragment(request, segments):
    """User-provided timestamped transcript. Never invents audio understanding."""
    words = set(re.findall(r'\w+', request.lower()))
    candidates = []
    for segment in segments:
        score = len(words & set(re.findall(r'\w+', str(segment['text']).lower())))
        start, end = float(segment['start']), float(segment['end'])
        if score and 0 <= start < end:
            candidates.append((score, start, end, segment['text']))
    if not candidates:
        raise ValueError('No transcript matches. Enter timestamps manually.')
    _, start, end, text = max(candidates, key=lambda x:x[0])
    return {'start':start, 'end':end, 'text':text, 'mode':'Keyword match in your transcript'}
