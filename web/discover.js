'use strict';
(() => {
 let local=[],web=[],catalogs=[],searched=false,busy=false,historyKey='',previewRequest;
 const resultGroups=['Из вашей библиотеки','Из интернета','Из аудиокаталогов'].map(name=>{
  const section=node('section',undefined,'resultGroup'),heading=node('h2',name);
  section.hidden=true;
  by('discoverResults').append(section);
  return {section,heading,rows:[]};
 });
 const progress=new Map();
 function updateProgress(){
  const jobs=[...progress.values()];
  const active=jobs.find(j=>j.status==='running')||jobs[0];
  by('discoverProgress').hidden=!busy&&!active;
  const label=active?jobLabels[active.kind]||'Обработка звука':'Ищем звук…';
  const text=label+(jobs.length>1?' · '+jobs.length+' задачи':'');
  const statusText=by('discoverProgressText');
  if(statusText.textContent!==text)statusText.textContent=text;
  const bar=by('discoverProgressBar');
  if(active?.progress>0)bar.value=active.progress;
  else bar.removeAttribute('value');
  by('cancelDiscover').hidden=!active;
 }
 bind('cancelDiscover',async()=>{
  await Promise.all([...progress.values()].map(j=>api('ai/cancel',{job_id:j.id})));
 });
 async function task(key,kind,data){
  try{return await runJob(kind,data,j=>{
   if(['queued','running'].includes(j.status))progress.set(key,j);
   else progress.delete(key);updateProgress();
  });}finally{progress.delete(key);updateProgress();}
 }
 function groups(){
  const seen=new Set();
  [local,web,catalogs].forEach((rows,index)=>{
   const group=resultGroups[index],isLocal=index===0;
   const unique=rows.filter(i=>{
    const key=isLocal?i.id:i.page_url||i.source_id;
    if(seen.has(key))return false;
    seen.add(key);
    return true;
   });
   if(unique.length===group.rows.length&&unique.every((row,j)=>row===group.rows[j]))return;
   group.rows=unique;
   group.section.hidden=!unique.length;
   group.section.replaceChildren(group.heading,...unique.map(i=>resultCard(i,isLocal)));
  });
  by('discoverEmpty').hidden=searched;
 }
 function resultCard(i,isLocal){
  const card=node('article',undefined,'resultCard'),badge=node('span',undefined,'resultIcon');badge.append(icon(isLocal?'grid':'wave'));
  const detail=node('div'),heading=node('h3',i.title,'resultTitle');
  let source=isLocal?'Моя библиотека':i.source;
  if(!isLocal)try{source=new URL(i.page_url).hostname.replace(/^www\./,'');}catch{}
  const duration=i.duration>0?fmt(i.duration,true):'Длительность станет известна после загрузки';
  const type=i.category||(i.download_url?'Аудиофайл':i.media_hint==='audio'?'Страница звука':'Веб-страница');
  const metaLine=node('p',[type,duration,source].filter(Boolean).join(' · '),'type');
  detail.append(heading,metaLine);
  const state=node('span',isLocal?'В библиотеке':i.can_import?'Доступность проверим при подготовке':'Только ссылка','availability');
  detail.append(state);
  const actions=node('div',undefined,'tools'),error=node('p',undefined,'inlineStatus');error.hidden=true;
  const opts={target:error};
  if(isLocal){
   actions.append(button('Play',()=>play(i.id),{...opts,glyph:'play'}),button('Preview',()=>playPreview('/api/file/'+i.id,i.title,i.id),opts),button('Edit',()=>openStudio(i.id),{...opts,glyph:'edit'}));
  }else if(!i.can_import){
   actions.append(link('Открыть источник ↗',i.page_url));
  }else{
   const body=()=>({source_id:i.source_id,category:by('importCategory').value});
   let pending,added=false;
   async function prepare(){
    status(error);
    pending??=task(Symbol(),'fetch',{...body(),add:false}).catch(err=>{pending=null;throw err;});
    const r=await pending;
    heading.textContent=r.item?.title||r.metadata.title;
    metaLine.textContent=['Аудиофайл',source].filter(Boolean).join(' · ');
    const duration=fmt(r.item?.duration??r.report?.output?.duration,true);
    const range=r.plan?.basis==='full_track'?['Вся запись']:r.plan?['Исходный отрезок '+fmt(r.plan.start,true)+'–'+fmt(r.plan.end,true)]:[];
    state.textContent=[added||r.item?'В библиотеке':'Готовый отрезок',duration,...range].join(' · ');
    return r;
   }
   const previewBtn=button('Послушать отрезок',async()=>{
    const request=previewRequest=Symbol();
    const version=previewVersion;
    const r=await prepare();
    if(!card.isConnected||view!=='discover'||previewRequest!==request||previewVersion!==version)return;
    await playPreview(r.item?'/api/file/'+r.item.id:r.preview_url,heading.textContent,r.item?.id);
    if(r.asset_id&&!added)addBtn.hidden=false;
   },{...opts,glyph:'play'});
   const addBtn=button('Добавить отрезок',async()=>{
    status(error);
    const draft=await pending;
    const r=await task(Symbol(),'fetch_commit',{asset_id:draft.asset_id});
    added=true;
    addBtn.hidden=true;
    heading.textContent=r.item.title;
    state.textContent='В библиотеке · '+fmt(r.item.duration,true);
    await sync();
    notify(r.duplicate?'Этот звук уже в библиотеке':'Добавлено: '+r.item.title);
   },{...opts,cls:'primary',glyph:'plus'});
   addBtn.hidden=true;
   const editBtn=button('Edit',async()=>{const r=await prepare();if(!card.isConnected||view!=='discover')return;if(r.item)await openStudio(r.item.id);else await openExternal(r);},{...opts,glyph:'edit'});
   actions.append(previewBtn,addBtn,editBtn);
  }
  card.append(badge,detail,actions);error.classList.add('resultError');card.append(error);
  if(!isLocal){
   const meta=node('details');meta.append(node('summary','Источник и сведения'),link('Открыть страницу ↗',i.page_url));
   if(i.reason)meta.append(node('p',i.reason,'muted'));
   if(i.license)meta.append(node('p',[i.license,i.author].filter(Boolean).join(' · '),'muted'));
   if(i.description)meta.append(node('p',i.description.slice(0,500),'muted'));card.append(meta);
  }
  return card;
 }
 function options(){
  return {query:by('discoverQuery').value.trim(),category:by('importCategory').value};
 }
 const history=by('recentQueries');
 function showHistory(values){
  const recent=values?.slice(0,12)||[];
  const key=JSON.stringify(recent);if(key===historyKey)return;historyKey=key;
  history.hidden=!recent.length;
  by('recentQueryList').replaceChildren(...recent.map(q=>{
   const entry=button(q,()=>{
    by('discoverQuery').value=q;
    history.open=false;
    by('discoverQuery').focus();
   },{cls:'quiet'});
   entry.title=q;
   return entry;
  }));
 }
 document.addEventListener('click',e=>{if(!history.contains(e.target))history.open=false;});
 history.addEventListener('keydown',e=>{
  if(e.key==='Escape'&&history.open){
   e.stopPropagation();history.open=false;history.querySelector('summary').focus();
  }
 });
 document.addEventListener('mimic:jobs',e=>showHistory(e.detail.finder_history));
 async function search(quick=false){
  if(busy)return;
  const body=options(),isLink=/^https?:\/\//i.test(body.query);
  const useWeb=isLink||by('webSource').checked,useCatalogs=!isLink&&by('catalogSource').checked,useLocal=!isLink&&by('localSource').checked;
  if(isLink)quick=false;
  if(!body.query){status('discoverStatus','Введите название или опишите звук.',true);by('discoverQuery').focus();return;}
  if(quick&&!useWeb&&!useCatalogs){status('discoverStatus','Для Quick Add выберите интернет или аудиокаталоги.',true);return;}
  if(!useWeb&&!useCatalogs&&!useLocal){status('discoverStatus','Выберите хотя бы один источник.',true);return;}
  busy=true;by('discoverGo').disabled=true;by('quickAdd').disabled=true;
  searched=true;local=[];web=[];catalogs=[];groups();status('discoverStatus');updateProgress();
  const errors=[];
  try{
   if(quick){
    const r=await task('quick','quick_add',{...body,scope:useWeb?'web':'catalogs'});
    const found=r.search||r;if(useWeb)web=found.external||[];else catalogs=found.external||[];showHistory(found.history);groups();
    if(r.item){await sync();notify(r.duplicate?'Этот звук уже в библиотеке':'Добавлено: '+r.item.title);status('discoverStatus');}
    else status('discoverStatus',found.topic_search?r.warning:'Quick Add не нашёл подтверждённый вариант. Выберите карточку и послушайте отрезок.');
    return;
   }
   const requests=[];
   const load=(key,kind,data,apply)=>requests.push(task(key,kind,data).then(r=>{apply(r);groups();}).catch(e=>errors.push(e.message)));
   if(useWeb)load('web','internet_search',{...body,scope:'web'},r=>{web=r.external||[];showHistory(r.history);if(!web.length&&r.warnings?.length)errors.push(...r.warnings);});
   if(useCatalogs)load('catalogs','internet_search',{...body,scope:'catalogs'},r=>{catalogs=r.external||[];showHistory(r.history);if(!catalogs.length&&r.warnings?.length)errors.push(...r.warnings);});
   if(useLocal&&items.length){
    const q=body.query.replace(/^(?:(?:найди|поищи|найти|мем|find|search)\s+)+/iu,'');
    const exact=items.filter(i=>[i.title,i.tags,i.description].join(' ').toLowerCase().includes(q.toLowerCase())).slice(0,30);
    local=exact;groups();
    load('local','search',{...body,local:true,external:false,favorites:by('favoriteBias').checked},r=>{const ids=new Set(exact.map(i=>i.id));local=[...exact,...(r.local||[]).filter(i=>!ids.has(i.id)&&i.score>=.18)].slice(0,30);});
   }
   await Promise.all(requests);
   if(errors.length)status('discoverStatus',errors.join(' · '),true);
   else if(!local.length&&!web.length&&!catalogs.length)status('discoverStatus','Совпадений нет. Попробуйте точное название или включите другой источник.');
   else if(useWeb&&web.length&&!web.some(r=>r.can_import&&r.media_hint==='audio')&&!isLink)
    status('discoverStatus','Готовый звук пока не найден. Можно вставить ссылку на MP3 или страницу отдельного звука.');
   else status('discoverStatus');
  }catch(e){status('discoverStatus',e.message,true);}
  finally{busy=false;by('discoverGo').disabled=false;by('quickAdd').disabled=false;updateProgress();}
 }
 by('discoverForm').onsubmit=e=>{e.preventDefault();search();};
 by('quickAdd').onclick=()=>search(true);
 document.querySelectorAll('.example').forEach(b=>b.onclick=()=>{by('discoverQuery').value=b.textContent;search();});
})();
