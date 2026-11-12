"""Validated editor plans. A model never supplies ffmpeg expressions or filesystem paths."""
import difflib
import math
import re

NUMBERS={'\u043e\u0434\u043d\u0443':1,'\u043e\u0434\u0438\u043d':1,'one':1,'\u0434\u0432\u0435':2,'\u0434\u0432\u0430':2,'two':2,'\u0442\u0440\u0438':3,'three':3,'\u0447\u0435\u0442\u044b\u0440\u0435':4,'four':4,'\u043f\u044f\u0442\u044c':5,'five':5,'\u0448\u0435\u0441\u0442\u044c':6,'six':6,'\u0441\u0435\u043c\u044c':7,'seven':7,'\u0432\u043e\u0441\u0435\u043c\u044c':8,'eight':8,'\u0434\u0435\u0432\u044f\u0442\u044c':9,'nine':9,'\u0434\u0435\u0441\u044f\u0442\u044c':10,'ten':10}


def number(text,default=3):
    m=re.search(r'\d+(?:[.,]\d+)?',text)
    if m:return float(m.group().replace(',','.'))
    for token in re.findall(r'\w+',text):
        if token in NUMBERS:return NUMBERS[token]
    return default


def normalized(text):return ' '.join(re.findall(r'\w+',str(text).lower()))


def phrase_span(phrase,segments):
    q=normalized(phrase)
    if not q:raise ValueError('Enter the phrase or select it from the transcript')
    best=None
    for start in range(len(segments)):
        for count in range(1,min(18,len(segments)-start)+1):
            sample=segments[start:start+count]
            text=normalized(' '.join(x['text'] for x in sample))
            ratio=difflib.SequenceMatcher(None,q,text).ratio()
            if q==text:ratio=1
            if best is None or ratio>best[0]:best=(ratio,float(sample[0]['start']),float(sample[-1]['end']),text)
    if not best or best[0]<.56:raise ValueError('No reliable phrase match. Select timestamps manually or refine the phrase.')
    return {'start':best[1],'end':best[2],'match':best[3],'match_score':round(best[0],3)}


def parse_rule(command,phrase=''):
    text=command.lower().strip()
    quotes=re.search(r'[«“"]([^»”"]+)[»”"]',command)
    selected=phrase or (quotes.group(1) if quotes else '')
    if re.fullmatch(r'(?:trim edge silence|remove leading and trailing silence|\u0443\u0431\u0435\u0440\u0438 \u0442\u0438\u0448\u0438\u043d\u0443 \u0432 \u043d\u0430\u0447\u0430\u043b\u0435 \u0438 (?:\u0432 )?\u043a\u043e\u043d\u0446\u0435)[.!]?',text):
        return {'operation':'trim_edges','mode':'Edge silence detection'}
    if re.fullmatch(r'(?:\u043e\u0441\u0442\u0430\u0432\u044c\s+|\u0432\u044b\u0431\u0435\u0440\u0438\s+|\u0441\u043e\u0445\u0440\u0430\u043d\u0438\s+)?(?:\u0432\u0435\u0441\u044c (?:\u0442\u0440\u0435\u043a|\u0437\u0432\u0443\u043a|\u0444\u0430\u0439\u043b)|\u0446\u0435\u043b\u0438\u043a\u043e\u043c|\u043f\u043e\u043b\u043d\u0443\u044e \u0432\u0435\u0440\u0441\u0438\u044e|(?:keep\s+)?(?:full|whole) (?:track|recording|audio))[.!]?',text):
        return {'operation':'process','mode':'Full recording'}
    interval=re.fullmatch(r'(?:(?:\u043e\u0441\u0442\u0430\u0432\u044c|\u0432\u044b\u0431\u0435\u0440\u0438|\u0432\u044b\u0440\u0435\u0436\u0438|trim|keep)\s+)?(?:\u0441\s+|from\s+)?'
                          r'(\d+(?::\d{2})?(?:[.,]\d+)?)\s*(?:[–—-]|\u0434\u043e|\u043f\u043e|to)\s*'
                          r'(\d+(?::\d{2})?(?:[.,]\d+)?)(?:\s+(?:\u0441\u0435\u043a\u0443\u043d\u0434\w*|seconds?))?[.!]?',text)
    if interval:
        def seconds(value):
            minutes,_,seconds=value.rpartition(':')
            return 60*int(minutes or 0)+float(seconds.replace(',','.'))
        return {'operation':'trim','start':seconds(interval[1]),'end':seconds(interval[2]),'mode':'Selected timestamps'}
    if any(w in text for w in ['\u043f\u0435\u0440\u0432\u044b\u0435','first']) and any(w in text for w in ['\u043e\u0431\u0440\u0435\u0436','\u0443\u0434\u0430\u043b','\u0443\u0431\u0435\u0440','remove','trim','cut']):
        return {'operation':'remove_first','seconds':number(text,5),'mode':'Exact command rule'}
    if any(w in text for w in ['\u0434\u0440\u043e\u043f','drop']) and any(w in text for w in ['\u043f\u0435\u0440\u0435\u0434','before']):
        return {'operation':'before_drop','seconds':number(text,3),'mode':'Energy onset candidate. Preview to confirm'}
    if re.search(r'\u043f\u043e\u0434\u0431\u0435\u0440\u0438 \u043c\u043e\u043c\u0435\u043d\u0442|\u044f\u0440\u043a\w+ (?:\u043c\u043e\u043c\u0435\u043d\u0442|\u0444\u0440\u0430\u0433\u043c\u0435\u043d\u0442)|\u044d\u043d\u0435\u0440\u0433\u0438\u0447\u043d\w+ (?:\u043c\u043e\u043c\u0435\u043d\u0442|\u0444\u0440\u0430\u0433\u043c\u0435\u043d\u0442)|\u0434\u0440\u043e\u043f|suggest.*highlight|highlight|drop|\u043f\u0440\u0438\u043f\u0435\u0432|chorus',text):
        return {'operation':'highlight','seconds':number(text,15),'mode':'Energy changes'}
    if any(w in text for w in ['\u0444\u0440\u0430\u0437','\u0440\u0435\u043f\u043b\u0438\u043a','phrase','sentence','after','\u043f\u043e\u0441\u043b\u0435']) or (quotes and any(w in text for w in ['\u043e\u0441\u0442\u0430\u0432','keep'])):
        after=any(w in text for w in ['\u043f\u043e\u0441\u043b\u0435','after'])
        if after and not selected:
            match=re.search(r'(?:\u043f\u043e\u0441\u043b\u0435|after)\s+(.+)$',command,re.I)
            if match and not re.search(r'\u0444\u0440\u0430\u0437|\u0440\u0435\u043f\u043b\u0438\u043a|phrase|sentence',match.group(1),re.I):selected=match.group(1).strip(' «»"')
        return {'operation':'after_phrase' if after and not re.search(r'\u0444\u0440\u0430\u0437\u0443\s+\u0438|phrase\s+and',text) else 'keep_phrase',
                'phrase':selected,'tail':number(text,3) if after else 0,'mode':'Whisper phrase search'}
    silence=any(w in text for w in ['\u0442\u0438\u0448\u0438\u043d','silence'])
    normalize=any(w in text for w in ['\u0433\u0440\u043e\u043c\u043a','\u0440\u043e\u0432\u043d\u0435\u0435','normaliz','loud','level','compress'])
    fade=any(w in text for w in ['\u043f\u043b\u0430\u0432\u043d','fade'])
    if silence or normalize or fade:
        fade_in=fade and any(w in text for w in ('\u043d\u0430\u0447\u0430\u043b','fade in'))
        return {'operation':'process','silence':silence,'normalize':normalize,'fade_in':number(text,.5) if fade_in else 0,'fade_out':number(text,.5) if fade and not fade_in else 0,'mode':'Exact command rule'}
    return None


def make_plan(spec,duration,segments=None,features=None):
    operation=spec.get('operation')
    start,end=0.,float(duration)
    fade_in,fade_out=float(spec.get('fade_in',0)),float(spec.get('fade_out',0))
    if not all(map(math.isfinite,(fade_in,fade_out))):raise ValueError('Enter a finite fade duration')
    result={'fade_in':min(5,max(0,fade_in)), 'silence':bool(spec.get('silence',False)),'normalize':bool(spec.get('normalize',False)),
            'fade_out':min(5,max(0,fade_out)), 'mode':str(spec.get('mode','Local model'))}
    if operation=='remove_first':start=float(spec.get('seconds',5))
    elif operation in ['keep_phrase','after_phrase']:
        span=phrase_span(spec.get('phrase',''),segments or [])
        start,end=span['start'],min(duration,span['end']+max(0,float(spec.get('tail',0))))
        if operation=='after_phrase':start=span['end']
        result.update(match=span['match'],match_score=span['match_score'])
    elif operation=='before_drop':
        candidates=(features or {}).get('onsets',[])
        if not candidates:raise ValueError('No clear energy onset found. Set the range manually.')
        onset=candidates[0]['time'];seconds=max(.25,min(30,float(spec.get('seconds',3))))
        start,end=max(0,onset-seconds),onset
        result['warning']='This is a candidate before an energy increase. Preview to confirm the drop.'
    elif operation=='highlight':
        candidates=(features or {}).get('onsets',[])
        if not candidates:
            raise ValueError('No clear energy change found. Select a waveform range or enter timestamps.')
        length=min(duration,max(.25,min(90,float(spec.get('seconds',15)))))
        onset=max(candidates,key=lambda point:point['strength'])['time']
        start=max(0,min(onset-length*.2,duration-length))
        end=start+length
        result['warning']='Selection based on energy changes. Preview to confirm the highlight.'
    elif operation=='trim_edges':
        edges=(features or {}).get('audible_edges')
        if edges:
            first,last=edges
            if first>=.15:start=first-.08
            if duration-last>=.15:end=min(duration,last+.08)
        if start==0. and end==duration:
            result['warning']='No quiet edges to trim. The full recording is selected.'
    elif operation=='trim':
        start,end=float(spec.get('start',0)),float(spec.get('end',duration))
    elif operation!='process':raise ValueError('Unknown operation. Refine the command or enter timestamps manually.')
    if not all(math.isfinite(v) for v in [start,end,result['fade_out']]) or not 0<=start<end<=duration+.05:
        raise ValueError('The command produced invalid boundaries. Check the recording duration and timestamps.')
    result.update(start=round(start,3),end=round(end,3),operation=operation)
    return result


def render_filters(plan):
    duration=plan['end']-plan['start']
    # Trim before reversing, so fade-out is applied at the actual end of the selection.
    filters=[f'atrim=duration={duration}', 'asetpts=PTS-STARTPTS']
    if plan['silence']:
        filters.append('silenceremove=start_periods=1:start_duration=0.08:start_threshold=-45dB:stop_periods=-1:stop_duration=0.25:stop_threshold=-45dB')
    if plan['normalize']:
        filters+=['acompressor=threshold=0.125:ratio=3:attack=10:release=150:makeup=1','loudnorm=I=-16:TP=-1.5:LRA=11']
    if plan['fade_in']:filters.append(f"afade=t=in:d={min(plan['fade_in'],duration)}")
    if plan['fade_out']:filters+=['areverse',f"afade=t=in:d={min(plan['fade_out'],duration)}",'areverse']
    return ','.join(filters)
