"""Live, keyless Wikimedia Commons official API; never an arbitrary URL downloader."""
import html
import re
from urllib.parse import urlencode,urlsplit
from .net import get_json

API='https://commons.wikimedia.org/w/api.php'


def clean(value):
    return html.unescape(re.sub('<[^>]+>',' ',str(value))).strip()[:2000]


def reusable(name):
    value=name.lower().strip()
    return value=='cc0' or 'public domain' in value or bool(re.fullmatch(r'cc by(?:-sa)? [1-4]\.0',value))


class Commons:
    def query(self,**params):
        return get_json(API+'?'+urlencode(dict(action='query',format='json',formatversion=2,**params)))
    def parse(self,page):
        info=(page.get('imageinfo') or [{}])[0]
        meta=info.get('extmetadata',{})
        value=lambda key:clean(meta.get(key,{}).get('value',''))
        url=info.get('url','');mime=info.get('mime','')
        if not (mime.startswith('audio/') or (mime=='application/ogg' and info.get('mediatype')=='AUDIO')) or urlsplit(url).hostname!='upload.wikimedia.org':return None
        license=value('LicenseShortName')
        permitted=reusable(license) and not value('Restrictions')
        size=int(info.get('size',0))
        duration=float(info.get('duration',0) or 0)
        for entry in info.get('metadata',[]):
            if str(entry.get('name','')).lower() in ['length','duration']:
                try:duration=float(entry['value'])
                except (ValueError,TypeError):pass
        supported=mime not in ['audio/midi','audio/x-midi','audio/x-mod'] and not url.lower().endswith(('.mid','.midi'))
        return {'source_id':'commons:'+str(page['pageid']),'title':page['title'].removeprefix('File:'),
                'source':'Wikimedia Commons','page_url':info.get('descriptionurl',''),
                'download_url':url,'license':license,'license_url':value('LicenseUrl'),
                'author':value('Artist') or value('Credit'),'description':value('ImageDescription'),
                'attribution':value('Attribution') or value('Credit'),
                'duration':duration,'bytes':size,'mime':mime,
                'can_import':permitted and supported and 0<size<=100*1024*1024 and duration<=1200,
                'reason':('Только страница: файл больше лимита 100 МБ / 20 минут' if size>100*1024*1024 or duration>1200 else
                          'Только страница: этот формат пока не декодируется' if not supported else
                          'Импорт с сохранением атрибуции и лицензии' if permitted else
                          'Только страница источника: лицензия или ограничения требуют проверки')}
    def search(self,query):
        query=re.sub(r'[^\w\s"\-]',' ',query)[:240]
        response=self.query(generator='search',gsrsearch='('+query+') filetype:audio',gsrnamespace=6,gsrlimit=15,
                            prop='imageinfo',iiprop='url|size|mime|mediatype|extmetadata|metadata')
        if 'error' in response:raise ValueError('Wikimedia: '+response['error'].get('info','ошибка поиска'))
        results=[]
        for page in response.get('query',{}).get('pages',[]):
            item=self.parse(page)
            if item:results.append(item)
        return results
    def resolve(self,id):
        if not re.fullmatch(r'commons:\d+',id):raise ValueError('Неизвестный источник')
        response=self.query(pageids=id.split(':')[1],prop='imageinfo',iiprop='url|size|mime|mediatype|extmetadata|metadata')
        pages=response.get('query',{}).get('pages',[])
        item=self.parse(pages[0]) if pages else None
        if not item or not item['can_import']:raise ValueError('Источник не разрешает автоматический импорт в этой версии')
        return item
