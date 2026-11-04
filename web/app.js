'use strict';
const $=selector=>document.querySelector(selector);
const by=id=>document.getElementById(id);
const icons={
 grid:'<rect x="3" y="3" width="7" height="7" rx="1.4"/><rect x="14" y="3" width="7" height="7" rx="1.4"/><rect x="3" y="14" width="7" height="7" rx="1.4"/><rect x="14" y="14" width="7" height="7" rx="1.4"/>',
 search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
 wave:'<path d="M2 12h3l2-5 3 12 3-15 3 13 2-5h4"/>',
 phone:'<rect x="6.5" y="2.5" width="11" height="19" rx="2.5"/><path d="M10.5 18.5h3"/>',
 settings:'<path d="M3 6h18M3 12h18M3 18h18"/><path d="M7 4v4m10 2v4M9 16v4" stroke-width="3"/>',
 plus:'<path d="M12 5v14M5 12h14"/>',
 play:'<path d="m8 4 13 8-13 8z" fill="currentColor" stroke="none"/>',
 pause:'<path d="M9 5v14m6-14v14" stroke-width="3"/>',
 stop:'<rect x="6" y="6" width="12" height="12" rx="1.5" fill="currentColor" stroke="none"/>',
 star:'<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9z"/>',
 edit:'<path d="m14 6 4 4M4 20l4-.8L20 7l-4-4L4 15z"/>',
 bolt:'<path d="M13 2 5 14h6l-1 8 9-12h-6z"/>',
 left:'<path d="m14 6-6 6 6 6"/>',right:'<path d="m10 6 6 6-6 6"/>',
 jobs:'<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
 volume:'<path d="M3 9h4l5-4v14l-5-4H3zM15 9a4 4 0 0 1 0 6m3-8a7 7 0 0 1 0 10"/>',
 qr:'<path d="M3 3h6v6H3zm12 0h6v6h-6zM3 15h6v6H3zm12 0h3v3h3v3h-6z"/>',
 refresh:'<path d="M20 11a8 8 0 1 0-2 6m2-13v7h-7"/>',
 close:'<path d="m6 6 12 12M18 6 6 18"/>',spark:'<path d="m12 2 2.5 7.5L22 12l-7.5 2.5L12 22l-2.5-7.5L2 12l7.5-2.5z"/>'
};
function icon(name){
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
 svg.setAttribute('class','icon');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.7');svg.setAttribute('stroke-linecap','round');svg.setAttribute('stroke-linejoin','round');svg.setAttribute('aria-hidden','true');svg.innerHTML=icons[name]||icons.wave;return svg;
}
function node(tag,text,cls){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;}
function button(text,fn,{cls='',glyph='',label='',target}={}){
 const b=node('button',text,cls);b.type='button';if(glyph)b.prepend(icon(glyph));if(label){b.setAttribute('aria-label',label);b.title=label;}if(fn)bind(b,fn,target);return b;
}
function status(target,text='',error=false){const el=typeof target==='string'?by(target):target;if(!el)return;el.hidden=!text;el.textContent=text;el.classList.toggle('error',error);}
let toastTimer;
function notify(text,error=false){status('toast',text,error);clearTimeout(toastTimer);toastTimer=setTimeout(()=>status('toast'),error?7500:3200);}
function bind(target,fn,errorTarget){
 const el=typeof target==='string'?by(target):target;
 el.addEventListener('click',async e=>{e.preventDefault();if(el.disabled)return;el.disabled=true;try{await fn(e);}catch(err){if(errorTarget)status(errorTarget,err.message,true);else notify(err.message,true);}finally{el.disabled=false;}});
}
async function api(path,data){
 const res=await fetch('/api/'+path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
 const body=await res.json();
 if(!res.ok){const err=Error(body.error||'Ошибка запроса');err.code=res.status;throw err;}return body;
}
function fmt(t,precise=false){
 if(!Number.isFinite(t)||t<0)return '—';
 const centi=Math.round(t*100),whole=precise?Math.floor(centi/100):Math.round(t);
 return Math.floor(whole/60)+':'+String(whole%60).padStart(2,'0')+(precise?'.'+String(centi%100).padStart(2,'0'):'');
}
function link(text,url){
 try{const u=new URL(url,location.href);if(!['https:','http:'].includes(u.protocol)||u.username||u.password)return node('span',text,'muted');const a=node('a',text);a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';return a;}catch{return node('span',text,'muted');}
}
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const jobLabels={internet_search:'Интернет-поиск',quick_add:'Быстрое добавление',search:'Поиск в библиотеке',fetch:'Подготовка звука',fetch_recut:'Обработка фрагмента',fetch_commit:'Добавление звука',render:'Обработка фрагмента',plan:'Команда для AI',commit:'Сохранение копии',metadata:'Название и теги',index:'Анализ звука',index_all:'Индексирование библиотеки',model:'Загрузка модели',model_import:'Импорт модели',asset_speech:'Распознавание речи'};
const jobStates={queued:'В очереди',running:'В работе',done:'Готово',failed:'Ошибка',cancelled:'Отменено'};
function jobCard(j){
 const box=node('article',undefined,'job'),head=node('div',undefined,'split');head.append(node('strong',jobLabels[j.kind]||j.kind),node('small',jobStates[j.status]||j.status));box.append(head);
 const active=['queued','running'].includes(j.status);
 if(active){const p=node('progress');p.max=1;p.value=j.progress||0;p.setAttribute('aria-label','Ход выполнения');box.append(p);}
 box.append(node('p',j.error||j.message||'',j.status==='failed'?'error':''));
 if(active){const cancel=button('Отменить',()=>api('ai/cancel',{job_id:j.id}),{cls:'quiet'});const row=node('div');row.append(cancel);box.append(row);}
 return box;
}
async function runJob(kind,data={},onProgress){
 const {job_id:id}=await api('ai/submit',{kind,...data});
 for(;;){
  const job=await api('ai/job/'+id);
  onProgress?.(job);
  if(job.status==='done')return job.result;
  if(job.status==='failed'||job.status==='cancelled')throw Error(job.error||'Задача отменена');
  await pause(850);
 }
}
let role='',items=[],audio={},revision=null,previewEpoch=null,view='soundboard',syncing;
const preview=new Audio();
preview.preload='metadata';
let previewClip=null,launchingClip=null,audioVersion=0,requestedVolume=null,previewVersion=0;

function stopPreview(){
 previewVersion++;
 previewClip=null;
 preview.pause();
 preview.removeAttribute('src');
 preview.load();
 renderPlaying();
}
function preparePreview(url,title,id){
 stopPreview();
 previewClip={title,id};
 preview.volume=requestedVolume??audio.volume??.65;
 preview.src=url;
}
async function playPreview(url,title,id){
 preparePreview(url,title,id);
 await preview.play();
}
for(const event of ['playing','pause','ended','error'])preview.addEventListener(event,renderPlaying);
function applyAudio(state){
 audio=state;
 audioVersion++;
 renderPlaying();
}
async function play(id){
 stopPreview();
 const request={title:items.find(i=>i.id===id)?.title||'Звук'};
 launchingClip=request;
 renderPlaying();
 try{
  const state=await api('play',{id});
  if(launchingClip===request)applyAudio(state);
 }finally{
  if(launchingClip===request){launchingClip=null;renderPlaying();}
  sync().catch(()=>{});
 }
}
function show(viewID){
 if(role!=='admin'&&viewID!=='soundboard')return;
 const section=by(viewID);if(!section?.classList.contains('view'))return;
 view=viewID;
 document.querySelectorAll('.view').forEach(s=>s.hidden=s.id!==view);
 document.querySelectorAll('#nav button').forEach(b=>b.dataset.view===view?b.setAttribute('aria-current','page'):b.removeAttribute('aria-current'));
 by('locationLabel').textContent=section.querySelector('h1').textContent;
 by('main').scrollTop=0;by('main').focus({preventScroll:true});
 document.dispatchEvent(new CustomEvent('mimic:view',{detail:view}));
}
let activeCategory='',favoritesOnly=false,query='',page=0,editing;
function libraryOptions(){
 const categories=[...new Set(items.map(i=>i.category).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
 by('category').replaceChildren(new Option('Все категории',''),...categories.map(c=>new Option(c,c)));
 if(!categories.includes(activeCategory))activeCategory='';
 by('category').value=activeCategory;
}
function renderLibrary(){
 const q=query.trim().toLocaleLowerCase();
 const filtered=items.filter(i=>(!activeCategory||i.category===activeCategory)&&(!favoritesOnly||i.favorite)&&(!q||[i.title,i.tags,i.category,i.description].join(' ').toLocaleLowerCase().includes(q)));
 const perPage=role==='remote'?32:48,pages=Math.max(1,Math.ceil(filtered.length/perPage));page=Math.min(page,pages-1);
 by('librarySummary').textContent=items.length?(filtered.length===items.length?'Звуков в коллекции: '+items.length:'Найдено '+filtered.length+' из '+items.length):'Ваша коллекция звуков.';
 by('empty').hidden=Boolean(filtered.length);
 by('emptyTitle').textContent=items.length?'Ничего не найдено':'Здесь будут ваши звуки';
 by('emptyDescription').textContent=items.length?'Попробуйте другой запрос или сбросьте фильтры.':role==='admin'?'Добавьте аудиофайл или найдите мем в Discover.':'Добавьте первый звук в VUPIO на компьютере.';
 by('pages').hidden=pages<=1;by('pageText').textContent=(page+1)+' / '+pages;by('prevPage').disabled=page===0;by('nextPage').disabled=page+1>=pages;
 const frag=document.createDocumentFragment();
 for(const i of filtered.slice(page*perPage,(page+1)*perPage)){
  if(role==='remote'){
   const tile=button(i.title,()=>play(i.id),{cls:'card remoteTile'});
   tile.dataset.id=i.id;
   frag.append(tile);
   continue;
  }
  const card=node('article',undefined,'card');
  card.dataset.id=i.id;
  const trigger=button('',()=>play(i.id),{cls:'cardTrigger',label:'Запустить '+i.title});
  const top=node('div',undefined,'split'),title=node('h3',i.title);
  const fav=button('',async()=>{await api('favorite',{id:i.id,favorite:!i.favorite});await sync();},{glyph:'star',cls:'quiet fav',label:'Избранное: '+i.title});fav.setAttribute('aria-pressed',String(Boolean(i.favorite)));
  top.append(title,fav);
  const tools=node('div',undefined,'tools');
  tools.append(button('Послушать',()=>playPreview('/api/file/'+i.id,i.title,i.id)),button('Edit',()=>openStudio(i.id),{glyph:'edit',label:'Редактировать аудио: '+i.title}),button('⋯',()=>openEditor(i),{label:'Карточка: '+i.title}));
  card.append(trigger,top,node('small',i.category+' · '+fmt(i.duration),'type'),tools);
  frag.append(card);
 }
 by('grid').replaceChildren(frag);renderPlaying();
}
function renderPlaying(){
 const active=new Set(audio.activeClips||[]);
 if(audio.playing)active.add(audio.playing);
 const listening=previewClip&&!preview.paused&&!preview.ended&&!preview.error;
 if(listening&&previewClip.id)active.add(previewClip.id);
 document.querySelectorAll('#grid .card').forEach(c=>c.classList.toggle('playing',active.has(c.dataset.id)));
 const current=items.find(i=>i.id===audio.playing)||items.find(i=>active.has(i.id));
 const mode=listening?'ПРЕДПРОСЛУШИВАНИЕ':launchingClip?'ЗАПУСК ЗВУКА':'СЕЙЧАС ИГРАЕТ';
 const title=listening?previewClip.title:launchingClip?launchingClip.title:
  current?(current.title+(active.size>1?' +' +(active.size-1):'')):
  audio.playing?'Проверочный сигнал':audio.error?'Аудиовыход недоступен':'Тишина';
 if(by('nowMode').textContent!==mode)by('nowMode').textContent=mode;
 const now=by('nowPlaying');
 if(now.textContent!==title)now.textContent=title;
 now.title=audio.error&&!listening&&!launchingClip?audio.error:title;
 const volume=requestedVolume??audio.volume??.65;
 preview.volume=volume;
 by('volume').value=volume;
 by('volumeValue').textContent=Math.round(100*volume)+'%';
 by('sideMic').classList.toggle('on',Boolean(audio.mic));
 by('sideAudio').textContent=audio.error?'Аудио недоступно':audio.mic?'Микрофон включён':'Микрофон выключен';
 by('sideRoute').textContent=audio.outputName||'Аудиовыход';
}
function sync(){
 if(syncing)return syncing;
 syncing=(async()=>{
  const version=audioVersion;
  const data=await api('state'),newRole=role!==data.role;
  role=data.role;
  if(version===audioVersion)audio=data.audio;
  if(previewEpoch!==null&&previewEpoch!==data.preview_stop_epoch)stopPreview();
  previewEpoch=data.preview_stop_epoch;
  const changed=newRole||revision!==data.revision;
  items=data.items;revision=data.revision;
  document.body.classList.toggle('remoteMode',role!=='admin');
  by('login').hidden=true;by('starting').hidden=true;by('shell').hidden=false;
  by('connection').classList.add('ready');by('connection').textContent=role==='remote'?'Компьютер подключён':'Локально';
  if(changed){libraryOptions();renderLibrary();document.dispatchEvent(new Event('mimic:library'));}else renderPlaying();
  document.dispatchEvent(new CustomEvent('mimic:audio',{detail:audio}));
 })().finally(()=>syncing=null);
 return syncing;
}
function showPair(error=''){role='';by('shell').hidden=true;by('starting').hidden=true;by('login').hidden=false;status('loginError',error,true);}
async function poll(){
 if(role)try{await sync();}catch(e){if(e.code===403)showPair('Подключите пульт заново.');else{by('connection').classList.remove('ready');by('connection').textContent='Нет связи';}}
 setTimeout(poll,900);
}
function openEditor(item){
 editing=item;for(const field of ['title','category','tags','description','license'])by('edit'+field[0].toUpperCase()+field.slice(1)).value=item[field]||'';
 status('cardStatus');by('editor').showModal();
}
for(const el of document.querySelectorAll('[data-icon]')){
 if(el.closest('#nav')){const name=el.textContent;el.replaceChildren(icon(el.dataset.icon),node('span',name,'navLabel'));el.setAttribute('aria-label',name);el.title=name;}
 else el.prepend(icon(el.dataset.icon));
}
by('nav').addEventListener('click',e=>{const target=e.target.closest('[data-view]');if(target)show(target.dataset.view);});
bind('findSound',()=>{show('discover');by('discoverQuery').focus();});
by('search').oninput=e=>{query=e.target.value;page=0;renderLibrary();};by('category').onchange=e=>{activeCategory=e.target.value;page=0;renderLibrary();};
by('favorites').onclick=()=>{favoritesOnly=!favoritesOnly;by('favorites').setAttribute('aria-pressed',String(favoritesOnly));page=0;renderLibrary();};
by('prevPage').onclick=()=>{page--;renderLibrary();by('main').scrollTop=0;};by('nextPage').onclick=()=>{page++;renderLibrary();by('main').scrollTop=0;};
async function stopAll(panic=false){
 launchingClip=null;
 stopPreview();
 applyAudio(await api(panic?'panic':'stop',{}));
 if(panic)notify('Клипы и микрофон отключены');
 await sync();
}
bind('stop',()=>stopAll());bind('panic',()=>stopAll(true));
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!e.repeat&&role&&!by('editor').open&&!['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName))stopAll(true).catch(err=>notify(err.message,true));});
let volumeTimer,savingVolume=false;
async function saveVolume(){
 if(savingVolume)return;
 savingVolume=true;
 try{
  while(requestedVolume!==null){
   const value=requestedVolume;
   try{
    const result=await api('volume',{value});
    applyAudio({...audio,volume:result.volume});
   }catch(error){notify(error.message,true);}
   if(requestedVolume===value)requestedVolume=null;
   renderPlaying();
  }
 }finally{savingVolume=false;}
}
by('volume').oninput=e=>{
 requestedVolume=Number(e.target.value);
 renderPlaying();
 clearTimeout(volumeTimer);
 volumeTimer=setTimeout(saveVolume,90);
};
by('uploadButton').onclick=()=>by('upload').click();
by('upload').onchange=async e=>{
 const file=e.target.files[0];if(!file)return;
 e.target.disabled=true;by('uploadButton').disabled=true;status('uploadStatus','Импортируем '+file.name+'…');
 try{
  if(file.size>100*1024*1024)throw Error('Файл больше 100 МБ. Выберите более короткий фрагмент.');
  const r=await fetch('/api/upload',{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file}),item=await r.json();
  if(!r.ok)throw Error(item.error);
  const title=file.name.replace(/\.[^.]+$/,'').slice(0,160)||'Новый звук';await api('edit',{id:item.id,title});await sync();status('uploadStatus');notify('Добавлено: '+title);
 }catch(err){status('uploadStatus',err.message,true);}finally{e.target.value='';e.target.disabled=false;by('uploadButton').disabled=false;}
};
by('closeEditor').onclick=()=>by('editor').close();
by('editForm').onsubmit=async e=>{e.preventDefault();const data={id:editing.id};for(const field of ['title','category','tags','description','license'])data[field]=by('edit'+field[0].toUpperCase()+field.slice(1)).value;
 try{await api('edit',data);by('editor').close();await sync();notify('Карточка сохранена');}catch(err){status('cardStatus',err.message,true);}
};
bind('cardMetadata',async()=>{const id=editing.id;status('cardStatus','Предлагаем название и теги…');const r=await runJob('metadata',{id});await sync();if(editing.id===id&&by('editor').open)for(const field of ['Title','Category','Tags'])by('edit'+field).value=r.item[field.toLowerCase()];status('cardStatus');notify('Название и теги обновлены');},'cardStatus');
bind('cardIndex',async()=>{status('cardStatus','Анализируем звук…');await runJob('index',{id:editing.id});status('cardStatus');notify('Индекс звука обновлён');},'cardStatus');
bind('deleteClip',async()=>{if(!confirm('Удалить «'+editing.title+'» из библиотеки VUPIO?'))return;await api('delete',{id:editing.id});by('editor').close();await sync();},'cardStatus');
by('pairForm').onsubmit=async e=>{e.preventDefault();try{await api('pair',{code:by('code').value,name:by('phoneName').value});by('code').value='';await sync();show('soundboard');}catch(err){status('loginError',err.message,true);}};
window.addEventListener('DOMContentLoaded',async()=>{
 document.querySelectorAll('.nativeOnly').forEach(el=>el.hidden=!window.webkit?.messageHandlers?.mimicNative);
 try{
  const key=new URLSearchParams(location.hash.slice(1)).get('admin');
  if(key){history.replaceState(null,'',location.pathname);await api('login',{key});}
  await sync();
 }catch(e){showPair(e.code===403?'':e.message);}
 poll();
 if('serviceWorker'in navigator&&window.isSecureContext)navigator.serviceWorker.register('/sw.js').catch(()=>{});
});
