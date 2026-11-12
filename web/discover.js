'use strict';
(() => {
 let local=[],web=[],catalogs=[],searched=false,busy=false,historyKey='',previewRequest,usageRequest=0;
 const webCards=new Map();
 async function refreshUsage(){
  const request=++usageRequest;
  const usage=await api('ai/web-usage').catch(()=>null);
  if(request!==usageRequest)return;
  const text=usage?.mode==='keyless'
   ?'Tavily · Keyless · '+usage.requests.toLocaleString()+' requests this month on this device'
   :Number.isFinite(usage?.remaining)
    ?'Tavily · '+usage.remaining.toLocaleString()+' plan credits left'
    :'Tavily · Usage unavailable';
  if(by('discoverUsage').textContent!==text)by('discoverUsage').textContent=text;
 }
 document.addEventListener('mimic:view',e=>{if(e.detail==='discover')refreshUsage();});
 const resultGroups=['From your library','From the web','From audio catalogs'].map(name=>{
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
  const label=active?jobLabels[active.kind]||'Processing sound':'Searching for sounds…';
  const text=label+(jobs.length>1?' · '+jobs.length+' tasks':'');
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
 async function task(key,kind,data,onProgress){
  try{return await runJob(kind,data,j=>{
   if(['queued','running'].includes(j.status))progress.set(key,j);
   else progress.delete(key);updateProgress();
   onProgress?.(j);
  },250);}finally{progress.delete(key);updateProgress();}
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
   if(index!==1){
    group.section.replaceChildren(group.heading,...unique.map(i=>resultCard(i,isLocal)));
    return;
   }
   const cards=unique.map(i=>{
    let card=webCards.get(i.source_id);
    if(!card){card=resultCard(i,false);webCards.set(i.source_id,card);}
    const reason=card.querySelector('.sourceReason');
    if(reason)reason.textContent=i.reason;
    return card;
   });
   if(cards.length)group.section.prepend(group.heading);
   for(const old of [...group.section.children])if(old!==group.heading&&!cards.includes(old))old.remove();
   let previous=group.heading;
   for(const card of cards){if(previous.nextElementSibling!==card)previous.after(card);previous=card;}
  });
  by('discoverEmpty').hidden=searched;
 }
 function resultCard(i,isLocal){
  const card=node('article',undefined,'resultCard'),badge=node('span',undefined,'resultIcon');badge.append(icon(isLocal?'grid':'wave'));
  const detail=node('div'),heading=node('h3',i.title,'resultTitle');
  let source=isLocal?'My library':i.source;
  if(!isLocal)try{source=new URL(i.page_url).hostname.replace(/^www\./,'');}catch{}
  const duration=i.duration>0?fmt(i.duration,true):'Duration available after download';
  const type=i.category||(i.download_url?'Audio file':i.media_hint==='audio'?'Sound page':'Web page');
  const metaLine=node('p',[type,duration,source].filter(Boolean).join(' · '),'type');
  detail.append(heading,metaLine);
  const state=node('span',isLocal?'In library':i.can_import?'Availability checked during preparation':'Link only','availability');
  detail.append(state);
  const actions=node('div',undefined,'tools'),error=node('p',undefined,'inlineStatus');error.hidden=true;
  const opts={target:error};
  if(isLocal){
   actions.append(button('Play',()=>play(i.id),{...opts,glyph:'play'}),button('Preview',()=>playPreview('/api/file/'+i.id,i.title,i.id),opts),button('Edit',()=>openStudio(i.id),{...opts,glyph:'edit'}));
  }else if(!i.can_import){
   actions.append(link('Open source ↗',i.page_url));
  }else{
   const body=()=>({source_id:i.source_id,category:by('importCategory').value,fast_preview:true});
   let pending,added=false;
   async function prepare(){
    status(error);
    pending??=task(Symbol(),'fetch',{...body(),add:false}).catch(err=>{pending=null;throw err;});
    const r=await pending;
    heading.textContent=r.item?.title||r.metadata.title;
    metaLine.textContent=['Audio file',source].filter(Boolean).join(' · ');
    const duration=fmt(r.item?.duration??r.report?.output?.duration,true);
    const range=r.plan?.basis==='full_track'?['Full recording']:r.plan?['Original range '+fmt(r.plan.start,true)+'–'+fmt(r.plan.end,true)]:[];
    state.textContent=[added||r.item?'In library':'Ready clip',duration,...range].join(' · ');
    return r;
   }
   const previewBtn=button('Preview clip',async()=>{
    const request=previewRequest=Symbol();
    const version=previewVersion;
    const r=await prepare();
    if(!card.isConnected||view!=='discover'||previewRequest!==request||previewVersion!==version)return;
    await playPreview(r.item?'/api/file/'+r.item.id:r.preview_url,heading.textContent,r.item?.id);
    if(r.asset_id&&!added)addBtn.hidden=false;
   },{...opts,glyph:'play'});
   const addBtn=button('Add clip',async()=>{
    status(error);
    const draft=await pending;
    const r=await task(Symbol(),'fetch_commit',{asset_id:draft.asset_id});
    added=true;
    addBtn.hidden=true;
    heading.textContent=r.item.title;
    state.textContent='In library · '+fmt(r.item.duration,true);
    await sync();
    notify(r.duplicate?'This sound is already in your library':'Added: '+r.item.title);
   },{...opts,cls:'primary',glyph:'plus'});
   addBtn.hidden=true;
   const editBtn=button('Edit full audio',async()=>{
    status(error);
    let r=pending?await pending:null;
    if(!r?.asset_id)r=await task(Symbol(),'fetch',{...body(),add:false,full_audio:true});
    if(!card.isConnected||view!=='discover')return;
    await openExternal(r,undefined,true);
   },{...opts,glyph:'edit'});
   actions.append(previewBtn,addBtn,editBtn);
  }
  card.append(badge,detail,actions);error.classList.add('resultError');card.append(error);
  if(!isLocal){
   const meta=node('details');meta.append(node('summary','Source details'),link('Open page ↗',i.page_url));
   if(i.reason)meta.append(node('p',i.reason,'muted sourceReason'));
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
  if(!body.query){status('discoverStatus','Enter a name or describe the sound.',true);by('discoverQuery').focus();return;}
  if(quick&&!useWeb&&!useCatalogs){status('discoverStatus','Enable Internet or Audio catalogs for Quick Add.',true);return;}
  if(!useWeb&&!useCatalogs&&!useLocal){status('discoverStatus','Select at least one source.',true);return;}
  busy=true;by('discoverGo').disabled=true;by('quickAdd').disabled=true;
  searched=true;local=[];web=[];catalogs=[];webCards.clear();groups();status('discoverStatus');updateProgress();
  const errors=[];
  try{
   if(quick){
    const r=await task('quick','quick_add',{...body,scope:useWeb?'web':'catalogs'});
    const found=r.search||r;if(useWeb)web=found.external||[];else catalogs=found.external||[];showHistory(found.history);groups();
    if(r.item){await sync();notify(r.duplicate?'This sound is already in your library':'Added: '+r.item.title);status('discoverStatus');}
    else status('discoverStatus',found.topic_search?r.warning:'Quick Add could not confirm a match. Select a card and preview the clip.');
    return;
   }
   const requests=[];
   const load=(key,kind,data,apply,onProgress)=>requests.push(task(key,kind,data,onProgress).then(r=>{apply(r);groups();}).catch(e=>errors.push(e.message)));
   let partialKey='';
   if(useWeb)load('web','internet_search',{...body,scope:'web',progressive:true},r=>{
    web=r.external||[];showHistory(r.history);if(!web.length&&r.warnings?.length)errors.push(...r.warnings);
   },j=>{
    if(j.status!=='running'||!j.result?.external?.length)return;
    const key=JSON.stringify(j.result.external);
    if(key!==partialKey){partialKey=key;web=j.result.external;groups();}
   });
   if(useCatalogs)load('catalogs','internet_search',{...body,scope:'catalogs'},r=>{catalogs=r.external||[];showHistory(r.history);if(!catalogs.length&&r.warnings?.length)errors.push(...r.warnings);});
   if(useLocal&&items.length){
    const q=body.query.replace(/^(?:(?:\u043d\u0430\u0439\u0434\u0438|\u043f\u043e\u0438\u0449\u0438|\u043d\u0430\u0439\u0442\u0438|\u043c\u0435\u043c|find|search)\s+)+/iu,'');
    const exact=items.filter(i=>[i.title,i.tags,i.description].join(' ').toLowerCase().includes(q.toLowerCase())).slice(0,30);
    local=exact;groups();
    load('local','search',{...body,local:true,external:false,favorites:by('favoriteBias').checked},r=>{const ids=new Set(exact.map(i=>i.id));local=[...exact,...(r.local||[]).filter(i=>!ids.has(i.id)&&i.score>=.18)].slice(0,30);});
   }
   await Promise.all(requests);
   if(errors.length)status('discoverStatus',errors.join(' · '),true);
   else if(!local.length&&!web.length&&!catalogs.length)status('discoverStatus','No matches. Try an exact name or enable another source.');
   else if(useWeb&&web.length&&!web.some(r=>r.can_import&&r.media_hint==='audio')&&!isLink)
    status('discoverStatus','No ready audio found yet. Paste an MP3 URL or an individual sound page.');
   else status('discoverStatus');
  }catch(e){status('discoverStatus',e.message,true);}
  finally{busy=false;by('discoverGo').disabled=false;by('quickAdd').disabled=false;updateProgress();if(useWeb&&!isLink)refreshUsage();}
 }
 document.addEventListener('mimic:radar-search',({detail})=>{
  show('discover');
  by('discoverQuery').value=detail.query;
  by('importCategory').value=detail.category;
  by('webSource').checked=true;
  by('discoverQuery').focus();
  search();
 });
 by('discoverForm').onsubmit=e=>{e.preventDefault();search();};
 by('quickAdd').onclick=()=>search(true);
 document.querySelectorAll('.example').forEach(b=>b.onclick=()=>{by('discoverQuery').value=b.textContent;search();});
})();
