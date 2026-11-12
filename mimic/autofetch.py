"""Download → inspect → analyze → cut → draft/commit. Originals stay in AI cache."""
import hashlib,json,math,re,time,uuid,wave
import sys
from .models import tool
from .net import catalog_download
from .features import analyze
from .editor import phrase_span,number,make_plan,render_filters
from .jobs import Cancelled

FORMATS='wav,mp3,ogg,flac,aac,mov,matroska,webm,aiff'
EVENTS={'scream':{'scream','screaming','shout','yell','battle_cry','children_shouting'},'cat':{'cat','meow','cat_meowing'},'music':{'music','background_music','musical_instrument','singing'},'failure':{'impact','explosion','thud','boing'}}

def pcm_hash(path):
    digest=hashlib.sha256()
    with wave.open(str(path)) as audio:
        while block:=audio.readframes(65536):
            digest.update(block)
    return digest.hexdigest()

def cut_plan(command,duration,analysis,previous=None):
    text=command.lower();start=0.;end=min(duration,8.);warning='Short opening clip. Sound identity has not been verified.';basis='initial'
    previous=previous or {'start':start,'end':end}
    if re.search(r'\u0440\u0430\u043d\u044c\u0448\u0435|earlier',text):start=max(0,float(previous['start'])-number(text,1));end=float(previous['end']);basis='relative';warning=''
    elif re.search(r'\u043e\u0431\u0440\u0435\u0436\u044c \u043a\u043e\u043d\u0435\u0446|shorten|trim.*end',text):start=float(previous['start']);end=float(previous['end'])-number(text,1);basis='relative';warning=''
    elif re.search(r'\u0441\u0435\u043a\u0443\u043d\u0434|seconds|\bsec\b',text) and not re.search(r'\u043a\u0440\u0438\u043a|scream|\u0434\u0440\u043e\u043f|drop|\u0444\u0440\u0430\u0437|phrase',text):end=min(duration,number(text,3));warning='';basis='duration'
    elif re.search(r'\u0444\u0440\u0430\u0437|\u0440\u0435\u043f\u043b\u0438\u043a|phrase',text):
        quoted=re.search(r'[«“"]([^»”"]+)[»”"]',command)
        if not quoted:raise ValueError('Enter a quoted phrase or select timestamps for an exact cut.')
        span=phrase_span(quoted.group(1),analysis.get('segments',[]));start=max(0,span['start']-.1);end=min(duration,span['end']+.15);warning='';basis='Whisper timestamps'
    elif re.search(r'\u043a\u0440\u0438\u043a|scream|\u0434\u0440\u043e\u043f|drop',text):
        labels={'scream','screaming','shout','yell','battle_cry','children_shouting'}
        windows=[w for w in analysis.get('windows',[]) if any(x['label'] in labels and x['confidence']>.08 for x in w.get('labels',[]))] if re.search(r'\u043a\u0440\u0438\u043a|scream',text) else []
        onset=windows[0]['start'] if windows else next((x['time'] for x in analysis.get('features',{}).get('onsets',[])),None)
        if onset is None:raise ValueError('Analysis could not identify the requested moment. Set the range manually.')
        start=max(0,onset-1);end=min(duration,onset+5);basis='SoundAnalysis window' if windows else 'energy onset';warning='Candidate based on the classifier window.' if windows else 'Energy onset candidate. Scream or drop not confirmed.'
    if not all(math.isfinite(v) for v in [start,end]) or not 0<=start<end<=duration+.01:raise ValueError('Invalid clip boundaries')
    return dict(start=round(start,3),end=min(duration,round(end,3)),basis=basis,warning=warning,normalize=True)

def radar_asset(id,data):
    return dict(asset_id=id,preview_url='/api/ai/asset/'+id,
                metadata=data['metadata'],report=data['report'],plan=data['report']['plan'])


class AutoFetch:
    def __init__(self,studio):self.s=studio
    def prepare(self,body,job,*,radar=False):
        started=time.monotonic()
        s=self.s;id=str(body['source_id']);saved=s.finder.saved(id);job.update(.05,'Checking · source availability')
        full_audio=not radar and body.get('full_audio') is True
        source=s.finder.resolve(id,job)
        key=uuid.uuid4().hex;raw=s.cache/(key+'.original');pcm=s.cache/(key+'.wav');preview=s.cache/(key+'.clip.wav')
        keep=False
        try:
            job.update(.15,'Downloading · audio file')
            if source.get('personal_import'):
                from .public_audio import download_public
                if radar:
                    download_public(source['download_url'],raw,job,maximum=8*1024*1024)
                else:
                    download_public(source['download_url'],raw,job)
            else:catalog_download(source['download_url'],raw,job)
            job.update(.45,'Checking · format, duration and quality')
            probe=json.loads(s.execute([tool('ffprobe'),'-v','error','-protocol_whitelist','file,pipe','-format_whitelist',FORMATS,'-show_format','-show_streams','-of','json',str(raw)],job,30))
            streams=probe.get('streams',[]);audio=[x for x in streams if x.get('codec_type')=='audio'];fmt=probe.get('format',{})
            duration=float(fmt.get('duration',0))
            if not audio or any(x.get('codec_type') not in {'audio'} for x in streams) or not math.isfinite(duration) or not 0<duration<=1200:raise ValueError('Use an audio-only file up to 20 minutes long')
            if radar and duration>120:
                raise ValueError('Trend Radar preloads sounds up to two minutes. Use Discover for this file.')
            stream=audio[0];rate=int(stream.get('sample_rate',0));channels=int(stream.get('channels',0))
            if rate<8000 or channels<1 or channels>8:raise ValueError('Unsupported audio parameters')
            bitrate=int(fmt.get('bit_rate',0) or 0)
            s.execute([tool('ffmpeg'),'-v','error','-nostdin','-protocol_whitelist','file,pipe','-format_whitelist',FORMATS,'-i',str(raw),'-map','0:a:0','-t','120' if radar else '1200','-ac','2','-ar','48000','-c:a','pcm_s16le',str(pcm)],job)
            # Hash decoded audio frames: detect same recording in different containers.
            sha=pcm_hash(pcm)
            with s.library.db() as db:duplicate=db.execute('SELECT * FROM finder_imports WHERE hash=?',(sha,)).fetchone()
            if duplicate and not full_audio:
                try:
                    item=s.library.get(duplicate['item']);return {'item':item,'duplicate':True,'warning':'This audio file is already in your library.'}
                except ValueError:pass
            job.update(.55,'Checking · analyzing audio')
            features=analyze(pcm)
            if features.get('peak',0)<.0001:raise ValueError('The file contains only silence')
            duration=features['duration']
            if radar:
                # The same decoded audio serves preview, Studio and Add.
                with wave.open(str(pcm)) as decoded:
                    duration=decoded.getnframes()/decoded.getframerate()
                plan=dict(start=0.,end=duration,normalize=False)
                metadata=dict(title=source['title'],category='Meme',tags='')
                report=dict(duration=duration,sha256=sha,plan=plan,output=features,analysis={})
                data=dict(source=source,report=report,metadata=metadata,original=raw.name,pcm=pcm.name)
                job.check()
                with s.library.db() as db:
                    db.execute('INSERT INTO ai_assets VALUES (?,?,?,?)',(key,pcm.name,json.dumps(data,ensure_ascii=False),time.time()))
                    db.execute('INSERT OR REPLACE INTO radar_clips VALUES (?,?)',(id,key))
                keep=True
                return radar_asset(key,data)
            # Bounded first 60 seconds; do not imply complete analysis of long music.
            sample=s.cache/(key+'.sample.wav')
            try:
                s.execute([tool('ffmpeg'),'-v','error','-nostdin','-i',str(pcm),'-t','60','-af','apad=pad_dur=2','-ar','48000','-ac','1',str(sample)],job)
                analysis=s.classify(sample,job)
            finally:sample.unlink(missing_ok=True)
            if analysis.get('error'):analysis={'labels':[],'warning':analysis['error']}
            analysis['features']=features;analysis['segments']=[]
            if any(x['label'] in {'speech','shout','scream','yell','narration'} and x['confidence']>.1 for x in analysis.get('labels',[])):
                try:
                    # Whisper only on bounded sample to protect 16GB machines.
                    short=s.cache/(key+'.speech.wav')
                    s.execute([tool('ffmpeg'),'-v','error','-nostdin','-i',str(pcm),'-t','60',str(short)],job)
                    analysis.update(s.transcribe(short,job))
                except ValueError as e:analysis['speech_warning']=str(e)
                finally:short.unlink(missing_ok=True)
            terms=saved.get('terms','');labels=analysis.get('labels',[])
            targets=set().union(*(v for k,v in EVENTS.items() if k in terms.lower()))
            evidence=max((float(x['confidence']) for x in labels if x['label'] in targets),default=0.)
            transcript=analysis.get('text','').lower()
            transcript_match=any(w in transcript for w in re.findall(r'\w+',terms.lower()) if len(w)>2)
            exact=bool(saved.get('named_query')) or bool(re.search(r'wide\s+putin|vine\s+boom|\u0430\u0443\u0440\u0430|aura|phonk|\u0444\u043e\u043d\u043a',saved.get('query',''),re.I))
            verified=(evidence>=.08 or transcript_match) and not exact
            report=dict(format=fmt.get('format_name'),duration=duration,sample_rate=rate,channels=channels,bitrate=bitrate,quality_warning='Low bitrate. Preview before adding.' if 0<bitrate<64000 else '',sha256=sha,labels=labels,analyzed_seconds=min(duration,60),content_match=verified,content_score=evidence,identity_verified=False,match_basis='SoundAnalysis classes and transcript metadata',analysis=analysis)
            if body.get('require_match') and not verified:raise ValueError('The audio did not confirm the query. Choose another result or preview it manually.')
            metadata=s.metadata(source['title']+' '+source['description'],analysis)
            if metadata.get('warning'):
                metadata['title']=source['title'][:160]
            category=str(body.get('category','All'))
            if category=='All' and re.search(r'\b(?:\u0442\u0440\u0435\u043a\w*|\u043f\u0435\u0441\u043d\w*|\u043c\u0443\u0437\u044b\u043a\w*|song|music|track|\u0444\u043e\u043d\u043a|phonk)\b',saved.get('query',''),re.I):
                category='Music'
            if category in {'Meme','Music','Reaction','Effect'}:metadata['category']=category
            command=str(body.get('command') or ('' if saved.get('topic_search') else saved.get('query','')))[:1000]
            full_track=full_audio or (metadata['category']=='Music' and not body.get('command'))
            if full_track:
                plan=dict(start=0.,end=duration,basis='full_track',warning='',normalize=not full_audio)
            else:
                plan=cut_plan(command,duration,analysis)
            job.update(.8,'Processing · preparing full audio' if full_audio else 'Processing · trimming and normalization')
            audio_filter='loudnorm=I=-16:TP=-1.5:LRA=11'
            if not full_track:
                audio_filter='silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB,'+audio_filter
            if full_audio:
                preview=pcm
                output=features
            else:
                s.execute([tool('ffmpeg'),'-v','error','-nostdin','-ss',str(plan['start']),'-i',str(pcm),'-t',str(plan['end']-plan['start']),'-af',audio_filter,'-ar','48000','-ac','2','-c:a','pcm_s16le',str(preview)],job)
                output=analyze(preview)
            if output.get('duration',0)<.05 or output.get('peak',0)<.0001:raise ValueError('No audible audio remains after processing')
            report['output']=output;report['plan']=plan
            report['processing_seconds']=round(time.monotonic()-started,3)
            if sys.platform=='darwin':
                import resource
                report['python_peak_rss_mib']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1048576,2)
                report['completed_child_peak_rss_mib']=round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss/1048576,2)
                report['memory_note']='macOS ru_maxrss: peak server and largest exited child; not total app/model RAM'
            try:
                s.models.path('embedding')
                vectors=s.models.embed(['task: search result | query: '+saved.get('query',''), 'Audio classes: '+', '.join(x['label'] for x in labels)+' Transcript: '+analysis.get('text','')[:1500]])
                a,b=vectors
                report['semantic_score']=sum(x*y for x,y in zip(a,b))/max(1e-9,math.sqrt(sum(x*x for x in a)*sum(x*x for x in b)))
                report['semantic_method']='Text embeddings of measured sound classes and transcript; not direct waveform/CLAP or identity fingerprint'
            except ValueError as e:report['semantic_warning']=str(e)[:250]
            data=dict(source=source,report=report,metadata=metadata,original=raw.name,pcm=pcm.name,query=saved.get('query',''))
            with s.library.db() as db:db.execute('INSERT INTO ai_assets VALUES (?,?,?,?)',(key,preview.name,json.dumps(data,ensure_ascii=False),time.time()))
            keep=True
            result=dict(asset_id=key,preview_url='/api/ai/asset/'+key,report=report,metadata=metadata,plan=plan,warning=plan['warning'] or ('' if verified else 'Audio match unverified. Check the preview.'))
            if body.get('add',True):result.update(self.commit(key,job,{'variant':True} if full_audio else None))
            job.update(1,'Ready · ready');return result
        finally:
            if not keep:
                for f in [raw,pcm,preview]:f.unlink(missing_ok=True)
    def editable_source(self,item):
        s=self.s
        with s.library.db() as db:
            asset=db.execute('SELECT asset_id FROM finder_edits WHERE item=?',(item,)).fetchone()
            if not asset:
                # Older imports store the original filename, prefixed with the initial asset ID.
                asset=db.execute("SELECT substr(original,1,instr(original,'.')-1) FROM finder_imports WHERE item=?",(item,)).fetchone()
        if not asset:
            return {}
        try:
            row,_=s.asset(asset[0])
        except ValueError:
            return {}
        data=json.loads(row['source'])
        if not data.get('pcm') or not (s.cache/data['pcm']).is_file():
            return {}
        report=data['report']
        return {'asset_id':row['id'],'metadata':{'title':s.library.get(item)['title']},'plan':report['plan'],
                'report':{'duration':report['duration'],'analysis':{'segments':report['analysis'].get('segments',[])}}}

    def commit(self,id,job,body=None):
        s=self.s;row,path=s.asset(id);data=json.loads(row['source'])
        if 'report' not in data:raise ValueError('This is not an AutoFetch draft')
        if not data['source'].get('personal_import'):s.finder.resolve(data['source']['source_id'])
        job.check()
        body=body or {}
        sha=data['report']['sha256']
        variant=body.get('variant') is True
        audio_hash=pcm_hash(path) if variant else None
        with s.library.db() as db:
            prior=db.execute('SELECT item FROM finder_imports JOIN clips ON item=id WHERE hash=?',(sha,)).fetchone()
            if variant:
                same=db.execute('SELECT item FROM finder_edits JOIN clips ON item=id WHERE hash=? AND audio_hash=?',
                                (sha,audio_hash)).fetchone()
                if same:
                    return {'item':s.library.get(same[0]),'duplicate':True}
        if prior:
            if not variant or (s.library.path(prior[0]).is_file() and pcm_hash(s.library.path(prior[0]))==audio_hash):
                return {'item':s.library.get(prior[0]),'duplicate':True}
        meta=dict(data['metadata'])
        for k in ('title','tags'):
            if body.get(k):meta[k]=str(body[k])
        license=json.dumps(data['source'],ensure_ascii=False)
        item=s.library.import_file(path,meta['title'],meta['category'],meta['tags'],data['source']['description'],license)
        with s.library.db() as db:
            if not prior:
                db.execute('INSERT OR REPLACE INTO finder_imports VALUES (?,?,?,?)',(sha,item['id'],data['original'],json.dumps(data['report'],ensure_ascii=False)))
            db.execute('INSERT INTO finder_edits VALUES (?,?,?,?)',(item['id'],id,sha,audio_hash))
        s.changed();return {'item':item}
    def recut(self,body,job):
        s=self.s;row,path=s.asset(body['asset_id']);data=json.loads(row['source'])
        if 'report' not in data:raise ValueError('Not an AutoFetch draft')
        report=data['report']
        if 'start' in body:
            plan=make_plan(dict(body,operation='trim'),report['duration'])
        else:
            selection=cut_plan(str(body.get('command','')),report['duration'],report['analysis'],report['plan'])
            plan=make_plan(dict(selection,operation='trim'),report['duration'])
            plan['warning']=selection['warning']
        key=uuid.uuid4().hex;target=s.cache/(key+'.clip.wav')
        try:
            s.execute([tool('ffmpeg'),'-v','error','-nostdin','-ss',str(plan['start']),'-i',str(s.cache/data['pcm']),'-af',render_filters(plan),'-ar','48000','-ac','2','-c:a','pcm_s16le',str(target)],job)
            output=analyze(target)
            if output['duration']<.01:raise ValueError('No audio remains after processing')
            report['plan']=plan;report['output']=output
            with s.library.db() as db:db.execute('INSERT INTO ai_assets VALUES (?,?,?,?)',(key,target.name,json.dumps(data,ensure_ascii=False),time.time()))
            return dict(asset_id=key,preview_url='/api/ai/asset/'+key,report=report,plan=plan,warning=plan.get('warning',''))
        except Exception:target.unlink(missing_ok=True);raise
    def quick(self,body,job):
        found=self.s.finder.search(body,job);errors=[]
        if found.get('topic_search'):
            return {'search': found, 'external': found['external'], 'history': found['history'],
                    'warning': 'Choose a result and preview the clip before adding.'}
        for candidate in [r for r in found['external'] if r['can_import']][:4]:
            job.check()
            try:
                r=self.prepare(dict(body,source_id=candidate['source_id'],require_match=True,add=True),job)
                r['search']=found;return r
            except Cancelled:raise
            except Exception as e:errors.append(candidate['title']+': '+str(e)[:350])
        return dict(search=found,external=found['external'],warnings=found['warnings']+errors,history=found['history'],warning='Quick Add could not confirm a matching audio file. Preview a result and select Add.')
