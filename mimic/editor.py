"""Validated editor plans. A model never supplies ffmpeg expressions or filesystem paths."""
import difflib
import math
import re

NUMBERS={'одну':1,'один':1,'one':1,'две':2,'два':2,'two':2,'три':3,'three':3,'четыре':4,'four':4,'пять':5,'five':5,'шесть':6,'six':6,'семь':7,'seven':7,'восемь':8,'eight':8,'девять':9,'nine':9,'десять':10,'ten':10}


def number(text,default=3):
    m=re.search(r'\d+(?:[.,]\d+)?',text)
    if m:return float(m.group().replace(',','.'))
    for token in re.findall(r'\w+',text):
        if token in NUMBERS:return NUMBERS[token]
    return default


def normalized(text):return ' '.join(re.findall(r'\w+',str(text).lower()))


def phrase_span(phrase,segments):
    q=normalized(phrase)
    if not q:raise ValueError('Введите нужную фразу или выберите её в расшифровке')
    best=None
    for start in range(len(segments)):
        for count in range(1,min(18,len(segments)-start)+1):
            sample=segments[start:start+count]
            text=normalized(' '.join(x['text'] for x in sample))
            ratio=difflib.SequenceMatcher(None,q,text).ratio()
            if q==text:ratio=1
            if best is None or ratio>best[0]:best=(ratio,float(sample[0]['start']),float(sample[-1]['end']),text)
    if not best or best[0]<.56:raise ValueError('Надёжного совпадения фразы нет. Выберите таймкоды вручную или уточните фразу.')
    return {'start':best[1],'end':best[2],'match':best[3],'match_score':round(best[0],3)}


def parse_rule(command,phrase=''):
    text=command.lower().strip()
    quotes=re.search(r'[«“"]([^»”"]+)[»”"]',command)
    selected=phrase or (quotes.group(1) if quotes else '')
    if re.fullmatch(r'(?:оставь\s+|выбери\s+|сохрани\s+)?(?:весь (?:трек|звук|файл)|целиком|полную версию|full track|whole track)[.!]?',text):
        return {'operation':'process','mode':'Полная запись'}
    interval=re.fullmatch(r'(?:(?:оставь|выбери|вырежи|trim|keep)\s+)?(?:с\s+|from\s+)?'
                          r'(\d+(?::\d{2})?(?:[.,]\d+)?)\s*(?:[–—-]|до|по|to)\s*'
                          r'(\d+(?::\d{2})?(?:[.,]\d+)?)(?:\s+(?:секунд\w*|seconds?))?[.!]?',text)
    if interval:
        def seconds(value):
            minutes,_,seconds=value.rpartition(':')
            return 60*int(minutes or 0)+float(seconds.replace(',','.'))
        return {'operation':'trim','start':seconds(interval[1]),'end':seconds(interval[2]),'mode':'По указанному времени'}
    if any(w in text for w in ['первые','first']) and any(w in text for w in ['обреж','удал','убер','remove','trim','cut']):
        return {'operation':'remove_first','seconds':number(text,5),'mode':'Точное правило команды'}
    if any(w in text for w in ['дроп','drop']) and any(w in text for w in ['перед','before']):
        return {'operation':'before_drop','seconds':number(text,3),'mode':'Кандидат по скачку энергии; проверьте на слух'}
    if re.search(r'подбери момент|ярк\w+ (?:момент|фрагмент)|энергичн\w+ (?:момент|фрагмент)|дроп|drop|припев|chorus',text):
        return {'operation':'highlight','seconds':number(text,15),'mode':'По изменению энергии'}
    if any(w in text for w in ['фраз','реплик','phrase','sentence','after','после']) or (quotes and any(w in text for w in ['остав','keep'])):
        after=any(w in text for w in ['после','after'])
        if after and not selected:
            match=re.search(r'(?:после|after)\s+(.+)$',command,re.I)
            if match and not re.search(r'фраз|реплик|phrase|sentence',match.group(1),re.I):selected=match.group(1).strip(' «»"')
        return {'operation':'after_phrase' if after and not re.search(r'фразу\s+и|phrase\s+and',text) else 'keep_phrase',
                'phrase':selected,'tail':number(text,3) if after else 0,'mode':'Whisper + поиск фразы'}
    silence=any(w in text for w in ['тишин','silence'])
    normalize=any(w in text for w in ['громк','ровнее','normaliz','loud','level','compress'])
    fade=any(w in text for w in ['плавн','fade'])
    if silence or normalize or fade:
        fade_in=fade and any(w in text for w in ('начал','fade in'))
        return {'operation':'process','silence':silence,'normalize':normalize,'fade_in':number(text,.5) if fade_in else 0,'fade_out':number(text,.5) if fade and not fade_in else 0,'mode':'Точное правило команды'}
    return None


def make_plan(spec,duration,segments=None,features=None):
    operation=spec.get('operation')
    start,end=0.,float(duration)
    fade_in,fade_out=float(spec.get('fade_in',0)),float(spec.get('fade_out',0))
    if not all(map(math.isfinite,(fade_in,fade_out))):raise ValueError('Укажите конечную длительность перехода')
    result={'fade_in':min(5,max(0,fade_in)), 'silence':bool(spec.get('silence',False)),'normalize':bool(spec.get('normalize',False)),
            'fade_out':min(5,max(0,fade_out)), 'mode':str(spec.get('mode','Локальная модель'))}
    if operation=='remove_first':start=float(spec.get('seconds',5))
    elif operation in ['keep_phrase','after_phrase']:
        span=phrase_span(spec.get('phrase',''),segments or [])
        start,end=span['start'],min(duration,span['end']+max(0,float(spec.get('tail',0))))
        if operation=='after_phrase':start=span['end']
        result.update(match=span['match'],match_score=span['match_score'])
    elif operation=='before_drop':
        candidates=(features or {}).get('onsets',[])
        if not candidates:raise ValueError('Выраженного скачка энергии не найдено. Укажите фрагмент вручную.')
        onset=candidates[0]['time'];seconds=max(.25,min(30,float(spec.get('seconds',3))))
        start,end=max(0,onset-seconds),onset
        result['warning']='Это кандидат перед ростом энергии, а не гарантированное распознавание музыкального дропа.'
    elif operation=='highlight':
        candidates=(features or {}).get('onsets',[])
        if not candidates:
            raise ValueError('Выраженного изменения энергии нет. Выберите фрагмент на волне или укажите время.')
        length=min(duration,max(.25,min(90,float(spec.get('seconds',15)))))
        onset=max(candidates,key=lambda point:point['strength'])['time']
        start=max(0,min(onset-length*.2,duration-length))
        end=start+length
        result['warning']='Фрагмент выбран по изменению энергии. Проверьте на слух, подходит ли этот момент.'
    elif operation=='trim':
        start,end=float(spec.get('start',0)),float(spec.get('end',duration))
    elif operation!='process':raise ValueError('Неизвестная операция. Уточните команду или задайте секунды вручную.')
    if not all(math.isfinite(v) for v in [start,end,result['fade_out']]) or not 0<=start<end<=duration+.05:
        raise ValueError('Команда дала невозможные границы. Проверьте длительность и секунды.')
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
