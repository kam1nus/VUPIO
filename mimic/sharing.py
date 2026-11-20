"""Explicit, authenticated sharing. Cloud requests never accept arbitrary hosts or paths."""
import hashlib,json,math,re,time,uuid,urllib.request,urllib.error
from pathlib import Path
from urllib.parse import urlsplit
from .account import WEBSITE,NoRedirect
from .models import tool
from .features import analyze

ID=re.compile(r'[a-f0-9]{32}')
HASH=re.compile(r'[a-f0-9]{64}')
MAX_AUDIO=2*1024*1024

class SharingConflict(ValueError):
    code='local_changes'


def parse_link(value,kind=None):
    value=str(value).strip()
    if ID.fullmatch(value) and kind in {'board','drop'}:return kind,value
    url=urlsplit(value)
    match=re.fullmatch(r'/(shared|drop)/([a-f0-9]{32})/?',url.path)
    if url.scheme!='https' or url.netloc!=urlsplit(WEBSITE).netloc or not match or url.username or url.password:
        raise ValueError('Paste a VUPIO shared board or Sound Drop link.')
    return ('board' if match[1]=='shared' else 'drop'),match[2]


class Cloud:
    def __init__(self,account):self.account=account
    def call(self,path,data=None,blob=None,duration=None):
        allowed=re.fullmatch(r'(overview|save-board|publish-drop|members|archive|revoke-drop|cleanup|asset|(?:board|drop)/[a-f0-9]{32}|audio/(?:board|drop)/[a-f0-9]{32}/[a-f0-9]{32})',path)
        if not allowed:raise ValueError('Unknown sharing action.')
        public=path.startswith(('drop/','audio/drop/'))
        headers={'User-Agent':'VUPIO-Account/1','Accept':'application/json'}
        if not public:
            if not self.account:raise ValueError('Sign in to VUPIO Account to use shared boards.')
            if not self.account.operation.acquire(timeout=20):raise ValueError('Account is busy. Try again in a moment.')
            try:token=self.account._load_token()
            finally:self.account.operation.release()
            if not token:raise ValueError('Sign in to VUPIO Account to use shared boards.')
            headers['Authorization']='Bearer '+token
        url=WEBSITE+'/api/share/'+path
        if blob is not None:
            if path!='asset' or len(blob)>MAX_AUDIO or not isinstance(duration,(int,float)) or not math.isfinite(duration):raise ValueError('Invalid shared audio upload.')
            headers['Content-Type']='audio/ogg';url+='?duration='+str(round(duration,3));payload=blob
        else:
            payload=json.dumps(data,ensure_ascii=False).encode() if data is not None else None
            if payload is not None:headers['Content-Type']='application/json'
        request=urllib.request.Request(url,data=payload,headers=headers)
        try:
            with urllib.request.build_opener(NoRedirect()).open(request,timeout=30) as response:
                limit=MAX_AUDIO if path.startswith('audio/') else 1048576
                result=response.read(limit+1)
                if len(result)>limit:raise ValueError('The sharing service returned an oversized file.')
                if path.startswith('audio/'):return result
                parsed=json.loads(result)
                if not isinstance(parsed,dict):raise ValueError('Invalid sharing response.')
                return parsed
        except urllib.error.HTTPError as error:
            try:message=str(json.loads(error.read(4096)).get('message') or '')[:500]
            except (ValueError,UnicodeError):message=''
            if not message:message={401:'Sign in to VUPIO Account again.',403:'This account cannot access this board or needs Pro to publish.',404:'This link is unavailable or you have not been invited.',409:'The shared board changed. Pull its latest version before pushing.',429:'Too many sharing requests. Wait a minute.'}.get(error.code,'The sharing service is unavailable. Try again later.')
            raise ValueError(message) from None
        except (urllib.error.URLError,TimeoutError,OSError):raise ValueError('Cannot reach VUPIO sharing. Check your connection and retry.') from None
        except (json.JSONDecodeError,UnicodeError):raise ValueError('The sharing service returned an invalid response.') from None


class Sharing:
    def __init__(self,studio,account=None,cloud=None):
        self.s,self.library=studio,studio.library
        self.cloud=cloud or Cloud(account)
        self.cache=studio.cache/'sharing'
        with self.library.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS local_share_links(kind TEXT,id TEXT,board TEXT,revision INTEGER,signature TEXT,bindings TEXT,PRIMARY KEY(kind,id))')
            db.execute('CREATE TABLE IF NOT EXISTS local_shared_audio(asset TEXT PRIMARY KEY,clip TEXT,metadata TEXT)')
    def links(self):
        with self.library.db() as db:return [dict(row) for row in db.execute('SELECT kind,id,board,revision FROM local_share_links')]
    def link(self,kind,id):
        with self.library.db() as db:row=db.execute('SELECT * FROM local_share_links WHERE kind=? AND id=?',(kind,id)).fetchone()
        return dict(row) if row else None
    def overview(self):return dict(self.cloud.call('overview'),local_links=self.links())
    def snapshot(self,kind,id):
        if kind not in {'board','drop'} or not ID.fullmatch(str(id)):raise ValueError('Invalid collection link.')
        data=self.cloud.call(kind+'/'+id);rows=data.get('manifest')
        if data.get('id')!=id or not isinstance(rows,list) or not 1<=len(rows)<=24:raise ValueError('Invalid shared collection.')
        seen=set()
        for row in rows:
            if not isinstance(row,dict) or not ID.fullmatch(str(row.get('id'))) or not HASH.fullmatch(str(row.get('hash'))) or row['id'] in seen:raise ValueError('Invalid shared audio details.')
            seen.add(row['id'])
            if type(row.get('bytes')) is not int or not 0<row['bytes']<=MAX_AUDIO or not isinstance(row.get('duration'),(int,float)) or not 0<row['duration']<=121:raise ValueError('Shared audio exceeds the import limits.')
            for field,limit in [('title',160),('category',80),('tags',500)]:
                if not isinstance(row.get(field),str) or len(row[field])>limit:raise ValueError('Invalid shared sound metadata.')
        if not isinstance(data.get('title'),str) or not 1<=len(data['title'])<=80:raise ValueError('Invalid shared board title.')
        return dict(data,local_link=self.link(kind,id))
    def _board(self,id):
        return next((b for b in self.library.boards() if b['id']==id),None)
    def _signature(self,id):
        board=self._board(id)
        if not board:return ''
        return self._signature_parts(board['title'],board['clips'])
    def _signature_parts(self,title,clips):
        entries=[]
        for clip in clips:
            item=self.library.get(clip);path=self.library.path(clip)
            try:stat=path.stat();file_sig=[stat.st_size,stat.st_mtime_ns]
            except OSError:file_sig=[]
            entries.append([clip,item['title'],item['category'],item['tags'],file_sig])
        return hashlib.sha256(json.dumps([title,entries],ensure_ascii=False).encode()).hexdigest()
    def _file_signature(self,id):
        stat=self.library.path(id).stat()
        return hashlib.sha256(json.dumps([id,stat.st_size,stat.st_mtime_ns]).encode()).hexdigest()
    def _selected(self,body,mode):
        board=self._board(body.get('board_id'))
        ids=body.get('ids')
        if mode=='board':
            if not board:raise ValueError('Choose a local soundboard to share.')
            ids=board['clips']
        elif ids is None:ids=board['clips'] if board else []
        limit=24 if mode=='board' else 12
        if not isinstance(ids,list) or not 1<=len(ids)<=limit or any(not isinstance(id,str) for id in ids) or len(ids)!=len(set(ids)):raise ValueError('Choose 1–'+str(limit)+' sounds to share.')
        selected=[self.library.get(id) for id in ids]
        for item in selected:
            if not isinstance(item['duration'],(int,float)) or not 0<item['duration']<=120.1:raise ValueError('Shared clips must be up to two minutes long. Shorten longer recordings in Studio first: '+item['title'])
            if not self.library.path(item['id']).is_file():raise ValueError('Audio file is missing: '+item['title'])
        return board,selected
    def _encode(self,item,job):
        self.cache.mkdir(exist_ok=True)
        key=self._file_signature(item['id']);encoded=self.cache/(key+'.ogg')
        if not encoded.is_file():
            temporary=self.cache/(uuid.uuid4().hex+'.ogg')
            try:
                self.s.execute([tool('ffmpeg'),'-v','error','-nostdin','-i',str(self.library.path(item['id'])),'-map','0:a:0','-t','120','-map_metadata','-1','-vn','-sn','-dn','-ar','48000','-ac','2','-c:a','libopus','-b:a','96k',str(temporary)],job)
                if not 32<temporary.stat().st_size<=MAX_AUDIO:raise ValueError('The encoded clip exceeds 2 MB. Shorten it in Studio.')
                temporary.replace(encoded)
            finally:temporary.unlink(missing_ok=True)
        return encoded
    def publish(self,body,job):
        self.s.pro.require();job.check();mode=body.get('mode')
        if mode not in {'board','drop'}:raise ValueError('Choose shared board or Sound Drop.')
        board,selected=self._selected(body,mode)
        title=str(body.get('title') or (board['title'] if board else 'Sound Drop')).strip();description=str(body.get('description') or '').strip()
        if not 1<=len(title)<=80 or len(description)>500:raise ValueError('Enter a title up to 80 characters and description up to 500.')
        current=None;bindings={}
        if body.get('cloud_id'):
            if mode!='board':raise ValueError('Sound Drops are snapshots. Publish a new drop instead of editing an old one.')
            current=self.snapshot('board',body['cloud_id'])
            if current.get('role') not in {'owner','editor'}:raise ValueError('Ask the owner for editor access before pushing changes.')
            if type(body.get('revision')) is not int or current.get('revision')!=body['revision']:raise ValueError('This board changed on another computer. Pull its latest version first.')
            link=self.link('board',current['id'])
            if not link or link['board']!=board['id'] or link['revision']!=current['revision']:raise ValueError('Your local copy is based on an older board version. Pull the latest version before pushing; keep unsent changes on another local board if needed.')
            bindings=json.loads(link['bindings'])
        existing={r['id']:r for r in current['manifest']} if current else {}
        manifest=[];new_bindings={}
        for index,item in enumerate(selected):
            job.check();job.update(.05+.8*index/len(selected),'Preparing shared audio · '+str(index+1)+'/'+str(len(selected)))
            signature=self._file_signature(item['id']);reuse=next((asset for asset,b in bindings.items() if b['clip']==item['id'] and b['signature']==signature and asset in existing),None)
            if reuse:asset=existing[reuse]
            else:
                file=self._encode(item,job);job.check();asset=self.cloud.call('asset',blob=file.read_bytes(),duration=item['duration'])
            if any(row['id']==asset['id'] for row in manifest):raise ValueError('The same audio appears twice. Remove the duplicate from this selection and retry.')
            entry={k:asset[k] for k in ('id','hash','bytes','duration')};entry.update(title=str(item['title'])[:160],category=str(item['category'] or 'Effect')[:80],tags=str(item['tags'] or '')[:500]);manifest.append(entry)
            new_bindings[asset['id']]={'clip':item['id'],'signature':signature,'metadata':{k:entry[k] for k in ('title','category','tags')}}
        job.check();job.update(.9,'Publishing reviewed collection…')
        payload=dict(title=title,description=description,manifest=manifest)
        if current:payload.update(id=current['id'],revision=body['revision'])
        result=self.cloud.call('save-board' if mode=='board' else 'publish-drop',payload)
        if mode=='board':
            self.library.save_board(title,board['id'])
            with self.library.db() as db:db.execute('INSERT OR REPLACE INTO local_share_links VALUES (?,?,?,?,?,?)',('board',result['id'],board['id'],result['revision'],self._signature(board['id']),json.dumps(new_bindings)))
        self.s.changed();return dict(result,url=WEBSITE+('/shared/' if mode=='board' else '/drop/')+result['id'])
    def _prepare_audio(self,kind,id,row,job):
        file=self.cache/(row['hash']+'.wav')
        if file.is_file():return file
        job.check();blob=self.cloud.call('audio/'+kind+'/'+id+'/'+row['id'])
        if not isinstance(blob,bytes) or len(blob)!=row['bytes'] or len(blob)>MAX_AUDIO or hashlib.sha256(blob).hexdigest()!=row['hash']:raise ValueError('Shared audio integrity check failed. Refresh the collection and retry.')
        self.cache.mkdir(exist_ok=True)
        raw=self.cache/(uuid.uuid4().hex+'.ogg');draft=self.cache/(uuid.uuid4().hex+'.wav')
        try:
            raw.write_bytes(blob)
            self.s.execute([tool('ffmpeg'),'-v','error','-nostdin','-i',str(raw),'-map','0:a:0','-t','121','-vn','-sn','-dn','-map_metadata','-1','-ar','48000','-ac','2','-c:a','pcm_s16le',str(draft)],job)
            features=analyze(draft)
            if not 0<features.get('duration',0)<=121:raise ValueError('Shared audio could not be decoded within the duration limit.')
            job.check();draft.replace(file)
        finally:raw.unlink(missing_ok=True);draft.unlink(missing_ok=True)
        return file
    def preview(self,body,job):
        kind,id=parse_link(body.get('id'),body.get('mode'));data=self.snapshot(kind,id)
        row=next((r for r in data['manifest'] if r['id']==body.get('asset_id')),None)
        if not row:raise ValueError('Choose a sound from this collection.')
        self._prepare_audio(kind,id,row,job);return {'preview_url':'/api/sharing/preview/'+row['hash'],'title':row['title']}
    def preview_path(self,key):
        if not HASH.fullmatch(str(key)):raise ValueError('Invalid preview.')
        file=self.cache/(key+'.wav')
        if not file.is_file():raise ValueError('Preview expired. Prepare it again.')
        return file
    def pull(self,body,job):
        kind,id=parse_link(body.get('id'),body.get('mode'));data=self.snapshot(kind,id);link=self.link(kind,id)
        existing=self._board(link['board']) if link and not body.get('new_copy') else None
        if existing and self._signature(existing['id'])!=link['signature'] and body.get('overwrite') is not True:raise SharingConflict('This local board has unsent changes. Pulling replaces its name, order and membership. Your audio files stay in All sounds. Confirm replacement or push your changes first.')
        baseline=self._signature(existing['id']) if existing else None
        rows=data['manifest']
        if kind=='drop' and body.get('ids') is not None:
            keys=body['ids']
            if not isinstance(keys,list) or not keys or any(not isinstance(key,str) for key in keys) or not set(keys)<={r['id'] for r in rows}:raise ValueError('Select sounds from this drop.')
            rows=[r for r in rows if r['id'] in keys]
        previous_bindings=json.loads(link['bindings']) if link else {}
        ids=[];bindings={};pending_metadata=[]
        for index,row in enumerate(rows):
            job.check();job.update(index/len(rows),'Importing shared sounds · '+str(index+1)+'/'+str(len(rows)))
            with self.library.db() as db:prior=db.execute('SELECT * FROM local_shared_audio WHERE asset=?',(row['id'],)).fetchone()
            if not prior and row['id'] in previous_bindings:
                binding=previous_bindings[row['id']]
                try:
                    if self._file_signature(binding['clip'])==binding['signature']:prior={'clip':binding['clip'],'metadata':json.dumps(binding['metadata'])}
                except (ValueError,OSError):pass
            item=None
            if prior:
                try:item=self.library.get(prior['clip']);self.library.path(item['id']).stat()
                except (ValueError,OSError):item=None
            if not item:
                file=self._prepare_audio(kind,id,row,job)
                item=self.library.import_file(file,row['title'],row['category'],row['tags'],'Shared via VUPIO',json.dumps({'source':WEBSITE+('/shared/' if kind=='board' else '/drop/')+id}))
            else:
                pending_metadata.append((item['id'],json.loads(prior['metadata']),row))
            meta={k:row[k] for k in ('title','category','tags')}
            with self.library.db() as db:db.execute('INSERT OR REPLACE INTO local_shared_audio VALUES (?,?,?)',(row['id'],item['id'],json.dumps(meta)))
            ids.append(item['id']);bindings[row['id']]={'clip':item['id'],'signature':self._file_signature(item['id']),'metadata':meta}
        job.check();board=existing['id'] if existing else uuid.uuid4().hex
        # Membership and ordering are committed together; audio imports can be safely retried.
        with self.library.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if existing and self._signature(existing['id'])!=baseline:raise SharingConflict('The local board changed while audio was downloading. Review your changes before pulling again.')
            for clip,previous,row in pending_metadata:
                current=db.execute('SELECT title,category,tags FROM clips WHERE id=?',(clip,)).fetchone()
                for field in ('title','category','tags'):
                    if current and current[field]==previous.get(field):db.execute('UPDATE clips SET '+field+'=? WHERE id=?',(row[field],clip))
            db.execute('INSERT INTO soundboards VALUES (?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title',(board,data['title']))
            db.execute('DELETE FROM soundboard_clips WHERE board_id=?',(board,))
            for position,clip in enumerate(dict.fromkeys(ids)):db.execute('INSERT INTO soundboard_clips VALUES (?,?,?)',(board,clip,position))
            entries=[]
            for clip in dict.fromkeys(ids):
                row=db.execute('SELECT title,category,tags FROM clips WHERE id=?',(clip,)).fetchone();stat=self.library.path(clip).stat()
                entries.append([clip,row['title'],row['category'],row['tags'],[stat.st_size,stat.st_mtime_ns]])
            signature=hashlib.sha256(json.dumps([data['title'],entries],ensure_ascii=False).encode()).hexdigest()
            db.execute('INSERT OR REPLACE INTO local_share_links VALUES (?,?,?,?,?,?)',(kind,id,board,data.get('revision',1),signature,json.dumps(bindings)))
        self.s.changed();return {'board_id':board,'count':len(set(ids)),'revision':data.get('revision',1)}
