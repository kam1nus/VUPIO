'use strict';
const $=selector=>document.querySelector(selector);
const by=id=>document.getElementById(id);
const icons={
 user:'<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
 grid:'<rect x="3" y="3" width="7" height="7" rx="1.4"/><rect x="14" y="3" width="7" height="7" rx="1.4"/><rect x="3" y="14" width="7" height="7" rx="1.4"/><rect x="14" y="14" width="7" height="7" rx="1.4"/>',
 search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
 radar:'<circle cx="12" cy="12" r="9"/><path d="M7 12a5 5 0 0 0 5 5m0-5 5-5"/><circle cx="12" cy="12" r="1" fill="currentColor"/>',
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
 grip:'<path d="M9 5h.01M15 5h.01M9 12h.01M15 12h.01M9 19h.01M15 19h.01" stroke-width="3"/>',
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
function button(text,fn,{cls='',glyph='',label='',target,onError}={}){
 const b=node('button',text,cls);b.type='button';if(glyph)b.prepend(icon(glyph));if(label){b.setAttribute('aria-label',label);b.title=label;}if(fn)bind(b,fn,target,onError);return b;
}
function status(target,text='',error=false){const el=typeof target==='string'?by(target):target;if(!el)return;el.hidden=!text;el.textContent=text;el.classList.toggle('error',error);}
let toastTimer;
function notify(text,error=false){status('toast',text,error);clearTimeout(toastTimer);toastTimer=setTimeout(()=>status('toast'),error?7500:3200);}
function bind(target,fn,errorTarget,onError){
 const el=typeof target==='string'?by(target):target;
 el.addEventListener('click',async e=>{e.preventDefault();if(el.disabled)return;el.disabled=true;try{await fn(e);}catch(err){if(errorTarget)status(errorTarget,err.message,true);else notify(err.message,true);onError?.(err);}finally{el.disabled=false;}});
}
async function api(path,data){
 const res=await fetch('/api/'+path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
 const body=await res.json();
 if(!res.ok){const err=Error(body.error||'Request failed');err.code=res.status;throw err;}return body;
}
function diagnosticsButton(stage,source){
 const copy=button('Copy diagnostics',async()=>{
  const code=copy.dataset.errorCode||'unclassified';
  const report=['VUPIO build '+(currentBuild??'unknown'),
   'Platform: '+(/Win/i.test(navigator.platform)?'Windows':/Mac/i.test(navigator.platform)?'macOS':'Other'),
   'Stage: '+(copy.dataset.stage||stage),'Source: '+source,'Error code: '+code].join('\n');
  if(navigator.clipboard?.writeText){
   try{await navigator.clipboard.writeText(report);notify('Diagnostics copied');return;}catch{}
  }
  const field=node('textarea');field.value=report;field.readOnly=true;
  field.setAttribute('aria-label','Diagnostics');document.body.append(field);field.select();
  try{if(!document.execCommand('copy'))throw Error('Could not copy diagnostics');}
  finally{field.remove();}
  notify('Diagnostics copied');
 },{cls:'quiet'});
 copy.hidden=true;
 return copy;
}
function setDiagnostic(button,error,stage){
 const codes=['private_address','network_dns','network_timeout','network_connect',
  'source_forbidden','source_rate_limit','source_missing','source_http'];
 button.dataset.errorCode=codes.includes(error?.code)?error.code:'unclassified';
 button.dataset.stage=stage||'';
 button.hidden=!error||Boolean(error.cancelled);
}
function diagnosticSource(host){
 const providers=['myinstants.com','tuna.voicemod.net','quicksounds.com','uwupad.me','archive.org','commons.wikimedia.org','openverse.org'];
 return providers.includes(host)?host:'External source';
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
const jobLabels={pro_generate:'AI collection',pro_prepare:'Preparing collection',pro_board:'Creating soundboard',radar:'Trend Radar',radar_clip:'Preloading sound',internet_search:'Internet search',quick_add:'Quick add',search:'Library search',fetch:'Preparing sound',fetch_recut:'Processing selection',fetch_commit:'Adding sound',render:'Processing selection',plan:'AI command',commit:'Saving copy',metadata:'Title and tags',index:'Audio analysis',index_all:'Indexing library',model:'Downloading model',model_import:'Importing model',asset_speech:'Speech transcription'};
const jobStates={queued:'Queued',running:'In progress',done:'Done',failed:'Error',cancelled:'Cancelled'};
function jobCard(j){
 const box=node('article',undefined,'job'),head=node('div',undefined,'split');head.append(node('strong',jobLabels[j.kind]||j.kind),node('small',jobStates[j.status]||j.status));box.append(head);
 const active=['queued','running'].includes(j.status);
 if(active){const p=node('progress');p.max=1;p.value=j.progress||0;p.setAttribute('aria-label','Progress');box.append(p);}
 box.append(node('p',j.error||j.message||'',j.status==='failed'?'error':''));
 if(active){const cancel=button('Cancel',()=>api('ai/cancel',{job_id:j.id}),{cls:'quiet'});const row=node('div');row.append(cancel);box.append(row);}
 return box;
}
async function runJob(kind,data={},onProgress,pollMs=850){
 const {job_id:id}=await api('ai/submit',{kind,...data});
 for(;;){
  const job=await api('ai/job/'+id);
  onProgress?.(job);
  if(job.status==='done')return job.result;
  if(job.status==='failed'||job.status==='cancelled'){const error=Error(job.error||'Task cancelled');error.code=job.result?.error_code||'';error.cancelled=job.status==='cancelled';throw error;}
  await pause(pollMs);
 }
}
let role='',items=[],audio={},revision=null,previewEpoch=null,view='soundboard',syncing,currentBuild;
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
 const request={title:items.find(i=>i.id===id)?.title||'Sound'};
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
 renderImportBoardHint();
 document.dispatchEvent(new CustomEvent('mimic:view',{detail:view}));
}
let activeCategory='',favoritesOnly=false,query='',page=0,editing;
let draggedCard, dropCard, swapping=false;

function clearBoardDrag(){
 draggedCard?.element.classList.remove('dragging');
 dropCard?.classList.remove('dropTarget');
 draggedCard=dropCard=null;
}

async function swapBoardCards(source,target,targetPage){
 if(swapping)return;
 swapping=true;
 const board=activeBoard;
 try{
  await api('board/swap',{source,target,board:board||null});
  if(targetPage!==undefined&&activeBoard===board)page=targetPage;
  if(syncing)await syncing.catch(()=>{});
  await sync();
  if(targetPage!==undefined&&view==='soundboard'&&activeBoard===board){
   const card=[...by('grid').children].find(el=>el.dataset.id===source);
   card?.querySelector('.cardGrip')?.focus();
  }
 }catch(err){notify(err.message,true);}
 finally{swapping=false;}
}

function boardGrip(item,card,filtered,index,perPage){
 const grip=button('',null,{glyph:'grip',cls:'quiet cardGrip',label:'Reorder '+item.title});
 grip.title='Drag to swap cards, or use the arrow keys';
 grip.setAttribute('aria-describedby','boardOrderHelp');
 grip.draggable=true;
 grip.addEventListener('keydown',e=>{
  const offset={ArrowUp:-1,ArrowLeft:-1,ArrowDown:1,ArrowRight:1}[e.key];
  if(!offset)return;
  e.preventDefault();
  const next=filtered[index+offset];
  if(next&&Boolean(next.favorite)===Boolean(item.favorite))
   swapBoardCards(item.id,next.id,Math.floor((index+offset)/perPage));
 });
 grip.addEventListener('dragstart',e=>{
  if(swapping||!e.dataTransfer){e.preventDefault();return;}
  clearBoardDrag();
  draggedCard={id:item.id,favorite:Boolean(item.favorite),element:card};
  e.dataTransfer.effectAllowed='move';
  e.dataTransfer.setData('text/plain',item.id);
  e.dataTransfer.setDragImage(card,card.clientWidth/2,24);
  card.classList.add('dragging');
 });
 grip.addEventListener('dragend',clearBoardDrag);
 const canDrop=()=>draggedCard&&draggedCard.id!==item.id&&draggedCard.favorite===Boolean(item.favorite);
 card.addEventListener('dragover',e=>{
  if(!canDrop())return;
  e.preventDefault();
  e.dataTransfer.dropEffect='move';
  if(dropCard!==card){
   dropCard?.classList.remove('dropTarget');
   dropCard=card;
   card.classList.add('dropTarget');
  }
 });
 card.addEventListener('dragleave',e=>{
  if(dropCard===card&&!card.contains(e.relatedTarget)){
   card.classList.remove('dropTarget');
   dropCard=null;
  }
 });
 card.addEventListener('drop',e=>{
  if(!canDrop())return;
  e.preventDefault();
  const source=draggedCard.id;
  clearBoardDrag();
  swapBoardCards(source,item.id);
 });
 return grip;
}

function categoryLabel(value){
 const legacy={'\u041c\u0435\u043c\u044b':'Memes','\u0422\u0440\u0435\u043a\u0438':'Tracks','\u042d\u0444\u0444\u0435\u043a\u0442\u044b':'Effects',
  '\u041c\u0443\u0437\u044b\u043a\u0430':'Music','\u0420\u0435\u0430\u043a\u0446\u0438\u0438':'Reactions'};
 return legacy[value]||value;
}

function libraryOptions(){
 const categories=[...new Set(boardLibraryItems().map(i=>i.category).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
 by('category').replaceChildren(new Option('All categories',''),...categories.map(c=>new Option(categoryLabel(c),c)));
 if(!categories.includes(activeCategory))activeCategory='';
 by('category').value=activeCategory;
}
function renderLibrary(){
 clearBoardDrag();
 const q=query.trim().toLocaleLowerCase();
 const boardItems=boardLibraryItems();
 const filtered=boardItems.filter(i=>(!activeCategory||i.category===activeCategory)&&(!favoritesOnly||i.favorite)&&(!q||[i.title,i.tags,i.category,i.description].join(' ').toLocaleLowerCase().includes(q)));
 const favoriteCount=filtered.filter(i=>i.favorite).length;
 const perPage=role==='remote'?32:48,pages=Math.max(1,Math.ceil(filtered.length/perPage));page=Math.min(page,pages-1);
 const boardName=currentSoundboard()?.title;
 by('librarySummary').textContent=(boardName?boardName+' · ':'')+(boardItems.length?(filtered.length===boardItems.length?boardItems.length+' sounds':'Found '+filtered.length+' of '+boardItems.length):'No sounds yet');
 by('empty').hidden=Boolean(filtered.length);
 by('emptyTitle').textContent=boardItems.length?'No results':activeBoard?'Build your board':'Your sounds will appear here';
 by('emptyDescription').textContent=boardItems.length?'Try another query or reset the filters.':role==='admin'?(activeBoard?'Use Manage board to choose existing sounds, or add audio and find a meme.':'Create a board for a game or a moment, then add your sounds.'):'Add sounds to this board in VUPIO on your computer.';
 by('boardOrderHelp').hidden=role!=='admin'||filtered.length<2;
 by('pages').hidden=pages<=1;by('pageText').textContent=(page+1)+' / '+pages;by('prevPage').disabled=page===0;by('nextPage').disabled=page+1>=pages;
 const frag=document.createDocumentFragment();
 for(const [offset,i] of filtered.slice(page*perPage,(page+1)*perPage).entries()){
  if(role==='remote'){
   const tile=button(i.title,()=>play(i.id),{cls:'card remoteTile'});
   tile.dataset.id=i.id;
   frag.append(tile);
   continue;
  }
  const card=node('article',undefined,'card');
  card.dataset.id=i.id;
  const trigger=button('',()=>play(i.id),{cls:'cardTrigger',label:'Play '+i.title});
  const top=node('div',undefined,'split'),title=node('h3',i.title),order=node('div',undefined,'cardOrder');
  const fav=button('',async()=>{
   await api('favorite',{id:i.id,favorite:!i.favorite});
   if(!i.favorite)page=0;
   if(syncing)await syncing.catch(()=>{});
   await sync();
  },{glyph:'star',cls:'quiet fav',label:'Favorite: '+i.title});
  fav.setAttribute('aria-pressed',String(Boolean(i.favorite)));
  if((i.favorite?favoriteCount:filtered.length-favoriteCount)>1)
   order.append(boardGrip(i,card,filtered,page*perPage+offset,perPage));
  order.append(fav);
  top.append(title,order);
  const tools=node('div',undefined,'tools');
  tools.append(button('Preview',()=>playPreview('/api/file/'+i.id,i.title,i.id)),button('Edit',()=>openStudio(i.id),{glyph:'edit',label:'Edit audio: '+i.title}),button('⋯',()=>openEditor(i),{label:'Details: '+i.title}));
  card.append(trigger,top,node('small',categoryLabel(i.category)+' · '+fmt(i.duration),'type'),tools);
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
 const mode=listening?'PREVIEW':launchingClip?'STARTING PLAYBACK':'NOW PLAYING';
 const title=listening?previewClip.title:launchingClip?launchingClip.title:
  current?(current.title+(active.size>1?' +' +(active.size-1):'')):
  audio.playing?'Test tone':audio.error?'Audio output unavailable':'Nothing playing';
 if(by('nowMode').textContent!==mode)by('nowMode').textContent=mode;
 const now=by('nowPlaying');
 if(now.textContent!==title)now.textContent=title;
 now.title=audio.error&&!listening&&!launchingClip?audio.error:title;
 const volume=requestedVolume??audio.volume??.65;
 preview.volume=volume;
 by('volume').value=volume;
 by('volumeValue').textContent=Math.round(100*volume)+'%';
 by('sideMic').classList.toggle('on',Boolean(audio.mic));
 by('sideAudio').textContent=audio.error?'Audio unavailable':audio.mic?'Microphone on':'Microphone off';
 by('sideRoute').textContent=audio.outputName||'Audio output';
}
function sync(){
 if(syncing)return syncing;
 syncing=(async()=>{
  const version=audioVersion;
  const data=await api('state'),newRole=role!==data.role;
  role=data.role;
  if(newRole&&role==='admin')schedulePublicUpdates();
  if(data.build){currentBuild=data.build;by('currentBuild').textContent='Installed build '+data.build;}
  if(version===audioVersion)audio=data.audio;
  if(previewEpoch!==null&&previewEpoch!==data.preview_stop_epoch)stopPreview();
  previewEpoch=data.preview_stop_epoch;
  const changed=newRole||revision!==data.revision;
  items=data.items;revision=data.revision;
  document.body.classList.toggle('remoteMode',role!=='admin');
  by('login').hidden=true;by('starting').hidden=true;by('shell').hidden=false;
  by('connection').classList.add('ready');by('connection').textContent=role==='remote'?'Computer connected':'Local';
  if(changed){applySoundboards(data.boards||[]);libraryOptions();renderLibrary();document.dispatchEvent(new Event('mimic:library'));}else renderPlaying();
  document.dispatchEvent(new CustomEvent('mimic:audio',{detail:audio}));
 })().finally(()=>syncing=null);
 return syncing;
}
function showPair(error=''){role='';by('shell').hidden=true;by('starting').hidden=true;by('login').hidden=false;status('loginError',error,true);}
async function poll(){
 if(role)try{await sync();}catch(e){if(e.code===403)showPair('Pair the remote again.');else{by('connection').classList.remove('ready');by('connection').textContent='Disconnected';}}
 setTimeout(poll,900);
}
function openEditor(item){
 editing=item;for(const field of ['title','category','tags','description','license'])by('edit'+field[0].toUpperCase()+field.slice(1)).value=item[field]||'';
 status('cardStatus');by('editor').showModal();
}
for(const el of document.querySelectorAll('[data-icon]')){
 if(el.closest('#nav')){const name=el.textContent.trim();el.replaceChildren(icon(el.dataset.icon),node('span',name,'navLabel'));el.setAttribute('aria-label',name);el.title=name;}
 else el.prepend(icon(el.dataset.icon));
}
by('nav').addEventListener('click',e=>{const target=e.target.closest('[data-view]');if(target)show(target.dataset.view);});
let updatePoll, updateCheck, updateInfo, publicInstalling=false;
const updateTarget='publicUpdateStatus';
function nativeUpdates(info){
 return info.platform==='win32'||(info.platform==='darwin'&&Boolean(window.webkit?.messageHandlers?.mimicNative));
}
function updateSize(bytes){return (bytes/1048576).toFixed(1)+' MB';}
function drawPublicUpdate(info,checked=true){
 updateInfo=info;
 const available=info.latest>info.installed;
 by('updatesNav').classList.toggle('hasUpdate',available);
 by('updatesNav').title=available?'Updates · New build available':'Updates';
 const compatible=available&&info.app_update&&nativeUpdates(info);
 const progress=by('publicUpdateProgress');
 by('autoUpdateOption').hidden=!info.supported||!nativeUpdates(info);
 if(typeof info.auto==='boolean')by('autoUpdate').checked=info.auto;
 by('downloadAppUpdate').hidden=!compatible||['ready','downloading','checking','preparing','installing'].includes(info.state);
 by('installAppUpdate').hidden=!compatible||info.state!=='ready'||publicInstalling;
 by('publicUpdateDownload').replaceChildren(...(available&&info.download?[link('Full installer ↗',info.download)]:[]));
 by('installAppUpdate').textContent=window.vupioNativeUpdater?'Update and restart':'Install update';
 progress.hidden=!['downloading','checking','preparing','installing'].includes(info.state);
 if(info.state==='downloading'&&info.size)progress.value=Math.min(1,info.received/info.size);
 else progress.removeAttribute('value');
 if(publicInstalling&&!window.vupioNativeUpdater)return;
 if(info.state==='failed'){status(updateTarget,info.error,true);return;}
 if(info.message){status(updateTarget,info.message);return;}
 if(!available){
  if(checked)status(updateTarget,info.latest?'Your build is up to date.':'No releases are available for this platform.');
  return;
 }
 if(info.state==='failed')status(updateTarget,info.error,true);
 else if(info.state==='ready')status(updateTarget,'Build '+info.latest+' is ready to install.');
 else if(info.state==='downloading')status(updateTarget,'Downloading '+updateSize(info.received)+' of '+updateSize(info.size)+'…');
 else status(updateTarget,compatible?'Build '+info.latest+' · '+updateSize(info.size):'Build '+info.latest+' is available as a full installer.');
}
async function watchPublicDownload(info){
 drawPublicUpdate(info);
 if(info.state!=='downloading'||updatePoll)return;
 updatePoll=true;
 try{
  do{
   await pause(750);
   if(role!=='admin')return;
   info=await api('updates/status');
   drawPublicUpdate(info);
  }while(info.state==='downloading');
 }finally{updatePoll=false;}
}
async function checkPublicUpdates(automatic=false){
 if(updateCheck||role!=='admin')return;
 if(window.vupioNativeUpdater){
  window.webkit.messageHandlers.mimicNative.postMessage('appUpdate:'+(automatic?'auto':'check'));
  return;
 }
 updateCheck=true;
 try{
  if(!automatic)status(updateTarget,'Checking GitHub…');
  const info=await api('updates');
  drawPublicUpdate(info);
  if(automatic&&info.auto&&info.app_update&&info.state==='idle'&&nativeUpdates(info))
   await watchPublicDownload({...await api('updates/download',{}),auto:info.auto});
  else if(info.state==='downloading')await watchPublicDownload(info);
 }finally{updateCheck=false;}
}
let periodicUpdateCheck;
function schedulePublicUpdates(){
 const check=()=>checkPublicUpdates(true).catch(()=>{});
 if(periodicUpdateCheck)return;
 setTimeout(check,3500);
 periodicUpdateCheck=setInterval(check,4*60*60*1000);
 api('updates/status').then(info=>{
  if(window.vupioNativeUpdater){
   window.webkit.messageHandlers.mimicNative.postMessage('appUpdate:'+(info.auto?'enable':'disable'));
   window.webkit.messageHandlers.mimicNative.postMessage('appUpdate:status');
  }else drawPublicUpdate(info,false);
 }).catch(()=>{});
}
bind('checkPublicUpdate',()=>checkPublicUpdates(),updateTarget);
bind('downloadAppUpdate',async()=>{
 if(window.vupioNativeUpdater){window.webkit.messageHandlers.mimicNative.postMessage('appUpdate:download');return;}
 await watchPublicDownload(await api('updates/download',{}));
},updateTarget);
by('autoUpdate').addEventListener('change',async e=>{
 const value=e.target.checked;
 try{
  await api('updates/preferences',{auto:value});
  if(window.vupioNativeUpdater)window.webkit.messageHandlers.mimicNative.postMessage('appUpdate:'+(value?'enable':'disable'));
  if(value)await checkPublicUpdates(true);
 }catch(err){e.target.checked=!value;status(updateTarget,err.message,true);}
});
window.vupioPublicUpdateStatus=(message,error)=>{
 publicInstalling=false;
 if(updateInfo)drawPublicUpdate(updateInfo);
 status(updateTarget,message,error);
};
window.vupioNativeUpdateState=info=>{
 publicInstalling=info.state==='installing';
 drawPublicUpdate(info);
};
bind('installAppUpdate',async()=>{
 const message=window.vupioNativeUpdater
  ?'Update and restart VUPIO now? Save your work in Studio before continuing.'
  :updateInfo?.platform==='darwin'
  ?'Install the update now? Save your work in Studio. If macOS Installer opens, follow its steps, then reopen VUPIO.'
  :'Install the update now? Save your work in Studio before continuing.';
 if(publicInstalling||!confirm(message))return;
 publicInstalling=true;
 by('installAppUpdate').hidden=true;
 status(updateTarget,'Preparing the update…');
 if(window.vupioNativeUpdater){window.webkit.messageHandlers.mimicNative.postMessage('appUpdate:install');return;}
 try{
  const result=await api('updates/install',{});
  if(result.platform==='macos')window.webkit.messageHandlers.mimicNative.postMessage('installPublicUpdate');
  else status(updateTarget,'Installing the update. Confirm Windows administrator access if requested. VUPIO will restart when ready.');
 }catch(err){
  window.vupioPublicUpdateStatus(err.message,true);
 }
},updateTarget);
bind('findSound',()=>{show('discover');by('discoverQuery').focus();});
by('search').oninput=e=>{query=e.target.value;page=0;renderLibrary();};by('category').onchange=e=>{activeCategory=e.target.value;page=0;renderLibrary();};
by('favorites').onclick=()=>{favoritesOnly=!favoritesOnly;by('favorites').setAttribute('aria-pressed',String(favoritesOnly));page=0;renderLibrary();};
by('prevPage').onclick=()=>{page--;renderLibrary();by('main').scrollTop=0;};by('nextPage').onclick=()=>{page++;renderLibrary();by('main').scrollTop=0;};
async function stopAll(panic=false){
 launchingClip=null;
 stopPreview();
 applyAudio(await api(panic?'panic':'stop',{}));
 if(panic)notify('Clips and microphone stopped');
 await sync();
}
bind('stop',()=>stopAll());bind('panic',()=>stopAll(true));
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!e.repeat&&role&&!document.querySelector('dialog[open]')&&!['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName))stopAll(true).catch(err=>notify(err.message,true));});
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
 const destination=activeBoard;
 e.target.disabled=true;by('uploadButton').disabled=true;status('uploadStatus','Importing '+file.name+'…');
 try{
  if(file.size>100*1024*1024)throw Error('File exceeds 100 MB. Choose a shorter recording.');
  const r=await fetch('/api/upload',{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file}),item=await r.json();
  if(!r.ok)throw Error(item.error);
  const title=file.name.replace(/\.[^.]+$/,'').slice(0,160)||'New sound';await api('edit',{id:item.id,title});await addImportedSound(item,destination);await sync();status('uploadStatus');notify('Added: '+title);
 }catch(err){status('uploadStatus',err.message,true);}finally{e.target.value='';e.target.disabled=false;by('uploadButton').disabled=false;}
};
by('closeEditor').onclick=()=>by('editor').close();
by('editForm').onsubmit=async e=>{e.preventDefault();const data={id:editing.id};for(const field of ['title','category','tags','description','license'])data[field]=by('edit'+field[0].toUpperCase()+field.slice(1)).value;
 try{await api('edit',data);by('editor').close();await sync();notify('Sound details saved');}catch(err){status('cardStatus',err.message,true);}
};
bind('cardMetadata',async()=>{const id=editing.id;status('cardStatus','Suggesting a title and tags…');const r=await runJob('metadata',{id});await sync();if(editing.id===id&&by('editor').open)for(const field of ['Title','Category','Tags'])by('edit'+field).value=r.item[field.toLowerCase()];status('cardStatus');notify('Title and tags updated');},'cardStatus');
bind('cardIndex',async()=>{status('cardStatus','Analyzing sound…');await runJob('index',{id:editing.id});status('cardStatus');notify('Audio index updated');},'cardStatus');
bind('deleteClip',async()=>{if(!confirm('Delete “'+editing.title+'” from your VUPIO library?'))return;await api('delete',{id:editing.id});by('editor').close();await sync();},'cardStatus');
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
