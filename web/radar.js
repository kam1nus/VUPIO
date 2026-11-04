'use strict';
(()=>{
 const kinds=[...by('radarKinds').querySelectorAll('button')];
 const region=by('radarRegion'),source=by('radarSource'),refresh=by('radarRefresh');
 const results=by('radarResults'),heading=by('radarHeading');
 const controls=[...kinds,region,source,refresh];
 let kind='memes',lastKey='',loadedAt=0,busy=false,previewRequest=0;
 let cards=[],selection=null,checking=false;

 async function validateClips(){
  if(checking)return;
  checking=true;
  try{
   while(view==='radar'&&selection){
    const batch=selection;
    if(batch.shown===batch.limit||batch.index===batch.rows.length){
     status('radarStatus',[
      batch.notice,
      batch.shown<batch.limit?'Доступных для прослушивания звуков: '+batch.shown+'.':'',
     ].filter(Boolean).join(' '));
     selection=null;
     break;
    }
    status('radarStatus','Проверяем и подгружаем звуки · '+batch.shown+'/'+batch.limit);
    const row=batch.rows[batch.index++];
    try{
     const ready=await runJob('radar_clip',{source_id:row.source_id},undefined,250);
     if(selection!==batch)continue;
     const result=card(row,true,batch.shown,batch.category,ready);
     cards.push(result);
     await result.warm();
     if(selection!==batch)continue;
     results.append(result.el);
     batch.shown++;
    }catch{/* Try the next chart entry before showing anything for this one. */}
   }
  }finally{checking=false;}
 }

 function clearCards(){
  selection=null;
  for(const card of cards)card.dispose?.();
  cards=[];
  results.replaceChildren();
 }

 function card(row,chart,index,category,initial){
  const el=node('article',undefined,'resultCard radarCard');
  const badge=node('span',chart?String(index+1):'','radarRank');
  if(!chart)badge.append(icon(category==='Meme'?'wave':'play'));
  const title=node('h3',row.title,'resultTitle');
  const detail=node('div');
  const subtitle=chart
   ? [row.artist,row.source_rank?'Место в последнем срезе: '+row.source_rank:'','Дней в топе: '+row.days].filter(Boolean).join(' · ')
   : [row.estimated_date&&'Дата по данным поиска: '+row.estimated_date.split('-').reverse().join('.'),row.excerpt].filter(Boolean).join(' · ');
  detail.append(title,node('p',subtitle,'muted'));
  const actions=node('div',undefined,'row wrap tools');
  const error=node('p',undefined,'inlineStatus resultError');
  error.hidden=true;
  error.setAttribute('role','status');
  const options={target:error};
  const card={el};
  if(row.source_id){
   const readiness=node('small',initial?.item?'В библиотеке':'Готов к прослушиванию','availability');
   const abort=new AbortController();
   let pending,prepared=initial,blobUrl;
   detail.append(readiness);
   const media=r=>r.item?'/api/file/'+r.item.id:r.preview_url;

   async function prepare(){
    if(prepared?.item&&!items.some(item=>item.id===prepared.item.id)){
     prepared=null;
     if(blobUrl){URL.revokeObjectURL(blobUrl);blobUrl=null;}
    }
    if(prepared)return prepared;
    readiness.textContent='Подгружаем звук…';
    if(!pending){
     pending=runJob('radar_clip',{source_id:row.source_id},undefined,250).then(r=>{
      prepared=r;
      readiness.textContent=r.item?'В библиотеке':'Готов к прослушиванию';
      return r;
     }).catch(e=>{
      readiness.textContent='Не удалось подгрузить';
      throw e;
     }).finally(()=>{pending=null;});
    }
    return pending;
   }

   card.warm=async()=>{
    const r=initial;
    // Keep short clips ready in the browser and larger clips ready on disk.
    if(abort.signal.aborted||(r.item?.duration??r.report?.duration??0)>20)return;
    const response=await fetch(media(r),{signal:abort.signal});
    if(!response.ok)throw Error('Предпросмотр недоступен');
    const blob=await response.blob();
    if(!blob.size)throw Error('Аудиофайл пуст');
    if(!abort.signal.aborted)blobUrl=URL.createObjectURL(blob);
   };
   card.dispose=()=>{
    abort.abort();
    if(blobUrl)URL.revokeObjectURL(blobUrl);
   };

   actions.append(button('Послушать',async()=>{
    status(error);
    const request=++previewRequest,version=previewVersion,r=await prepare();
    if(el.isConnected&&view==='radar'&&version===previewVersion&&request===previewRequest)
     await playPreview(blobUrl||media(r),r.item?.title||row.title,r.item?.id);
   },{...options,glyph:'play'}),button('Add',async()=>{
    status(error);
    const r=await prepare();
    readiness.textContent=r.item?'В библиотеке':'Добавляем…';
    try{
     const saved=r.item?r:await runJob('fetch_commit',{asset_id:r.asset_id},undefined,250);
     await sync();
     prepared=saved;
     readiness.textContent='В библиотеке';
     notify(saved.duplicate?'Этот звук уже в библиотеке':'Добавлено: '+saved.item.title);
    }catch(e){
     readiness.textContent='Готов к прослушиванию';
     throw e;
    }
   },{...options,cls:'primary',glyph:'plus'}),button('В Studio',async()=>{
    status(error);
    const r=await prepare();
    if(!el.isConnected||view!=='radar')return;
    if(r.item)await openStudio(r.item.id);else await openExternal(r);
   },{...options,glyph:'edit'}));
  }else{
   const add=button('Add',null,{glyph:'plus'});
   add.disabled=true;
   add.title='Для добавления нужен отдельный аудиофайл';
   detail.append(node('small','Ссылка на источник · файл для добавления не найден','availability'));
   actions.append(add,button('Найти аудио',()=>{
    document.dispatchEvent(new CustomEvent('mimic:radar-search',{detail:{
     query:[row.artist,row.title].filter(Boolean).join(' '),category,
    }}));
   },{glyph:'search'}));
  }
  actions.append(link('Открыть источник ↗',row.url));
  el.append(badge,detail,actions,error);
  return card;
 }

 function render(data,category){
  by('radarTitle').textContent=data.title;
  const date=data.day?.split('-').reverse().join('.');
  const count=data.rows.length;
  const coverage=data.days===1?'Текущий срез'
   : data.days===7?'Топ за 7 дней'
   : 'Топ по доступным срезам за 7 дней';
  by('radarScope').textContent=data.chart
   ? data.days?[coverage,'Дней со срезами: '+data.days+' из 7',date&&'Обновлено '+date].filter(Boolean).join(' · '):'Региональный чарт'
   : 'Веб-поиск за неделю · страна учитывается в запросе · сортировка по релевантности';
  by('radarSourceLink').replaceChildren(link(data.chart?'Данные чарта ↗':'Открыть платформу ↗',data.source_url));
  heading.hidden=false;
  status('radarStatus',[
   data.warning,data.stale?'Показан сохранённый результат.':'',
   !count&&!data.warning?(data.chart?'В чарте пока нет записей.':'Подходящих публичных роликов или страниц звуков не найдено. Попробуйте другую страну или платформу.'):'',
  ].filter(Boolean).join(' '),Boolean(data.warning&&!count));
  clearCards();
  if(data.playable_chart&&count){
   selection={rows:data.rows.filter(row=>row.source_id),category,index:0,shown:0,limit:data.limit,
              notice:[data.warning,data.stale?'Показан сохранённый результат.':''].filter(Boolean).join(' ')};
   validateClips();
  }else{
   cards=data.rows.map((row,i)=>card(row,data.chart,i,category));
   results.append(...cards.map(card=>card.el));
  }
 }

 async function load(force=false){
  const key=[kind,region.value,source.value].join('/');
  if(busy||(!force&&key===lastKey&&Date.now()-loadedAt<300000))return;
  busy=true;
  controls.forEach(el=>el.disabled=true);
  results.setAttribute('aria-busy','true');
  if(key!==lastKey)heading.hidden=true;
  clearCards();
  status('radarStatus','Обновляем подборку…');
  try{
   const data=await runJob('radar',{category:kind,region:region.value,source:source.value,force},job=>{
    if(job.status==='running')status('radarStatus',job.message||'Обновляем подборку…');
   });
   render(data,kind==='memes'?'Meme':'Music');
   lastKey=key;
   loadedAt=Date.now();
  }catch(e){status('radarStatus',e.message,true);}
  finally{
   busy=false;
   results.removeAttribute('aria-busy');
   controls.forEach(el=>el.disabled=false);
  }
 }

 for(const tab of kinds)tab.addEventListener('click',()=>{
  kind=tab.dataset.kind;
  for(const other of kinds)other.setAttribute('aria-pressed',String(tab===other));
  load();
 });
 for(const filter of [region,source])filter.addEventListener('change',()=>load());
 refresh.addEventListener('click',()=>load(true));
 document.addEventListener('mimic:view',e=>{if(e.detail==='radar'){load();validateClips();}});
})();
