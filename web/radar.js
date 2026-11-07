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
      batch.shown<batch.limit?'Playable sounds: '+batch.shown+'.':'',
      batch.failed?'Unavailable sounds skipped: '+batch.failed+'.':'',
      !batch.shown&&batch.lastError?batch.lastError:'',
     ].filter(Boolean).join(' '),!batch.shown&&Boolean(batch.failed));
     selection=null;
     break;
    }
    status('radarStatus','Checking and preloading sounds · '+batch.shown+'/'+batch.limit);
    const row=batch.rows[batch.index++];
    let result;
    try{
     const ready=await runJob('radar_clip',{source_id:row.source_id},undefined,250);
     if(selection!==batch)continue;
     result=card(row,true,batch.shown,batch.category,ready);
     await result.warm();
     if(selection!==batch){result.dispose?.();continue;}
     cards.push(result);
     results.append(result.el);
     batch.shown++;
     batch.denied=0;
    }catch(error){
     result?.dispose?.();
     if(selection!==batch)continue;
     batch.failed++;batch.lastError=error.message;
     batch.denied=error.code==='source_forbidden'?batch.denied+1:0;
     // A dead sound is replaced. A shared DNS/network/rate limit is reported
     // immediately instead of repeating the same failure for thirty cards.
     if(['network_dns','network_connect','network_timeout','source_rate_limit'].includes(error.code)||batch.denied>=3){
      status('radarStatus',[batch.notice,'Playable sounds: '+batch.shown+'.',error.message,'Refresh after the connection is restored.'].filter(Boolean).join(' '),true);
      selection=null;break;
     }
    }
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
   ? [row.artist,row.source_rank?'Latest source rank: '+row.source_rank:'','Days in top chart: '+row.days].filter(Boolean).join(' · ')
   : [row.estimated_date&&'Search estimated date: '+row.estimated_date.split('-').reverse().join('.'),row.excerpt].filter(Boolean).join(' · ');
  detail.append(title,node('p',subtitle,'muted'));
  const actions=node('div',undefined,'row wrap tools');
  const error=node('p',undefined,'inlineStatus resultError');
  error.hidden=true;
  error.setAttribute('role','status');
  const options={target:error};
  const card={el};
  if(row.source_id){
   const readiness=node('small',initial?.item?'In library':'Ready to preview','availability');
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
    readiness.textContent='Preloading sound…';
    if(!pending){
     pending=runJob('radar_clip',{source_id:row.source_id},undefined,250).then(r=>{
      prepared=r;
      readiness.textContent=r.item?'In library':'Ready to preview';
      return r;
     }).catch(e=>{
      readiness.textContent='Could not preload';
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
    if(!response.ok)throw Error('Preview unavailable');
    const blob=await response.blob();
    if(!blob.size)throw Error('Audio file is empty');
    if(!abort.signal.aborted)blobUrl=URL.createObjectURL(blob);
   };
   card.dispose=()=>{
    abort.abort();
    if(blobUrl)URL.revokeObjectURL(blobUrl);
   };

   actions.append(button('Preview',async()=>{
    status(error);
    const request=++previewRequest,version=previewVersion,r=await prepare();
    if(el.isConnected&&view==='radar'&&version===previewVersion&&request===previewRequest)
     await playPreview(blobUrl||media(r),r.item?.title||row.title,r.item?.id);
   },{...options,glyph:'play'}),button('Add',async()=>{
    status(error);
    const r=await prepare();
    readiness.textContent=r.item?'In library':'Adding…';
    try{
     const saved=r.item?r:await runJob('fetch_commit',{asset_id:r.asset_id},undefined,250);
     await sync();
     prepared=saved;
     readiness.textContent='In library';
     notify(saved.duplicate?'This sound is already in your library':'Added: '+saved.item.title);
    }catch(e){
     readiness.textContent='Ready to preview';
     throw e;
    }
   },{...options,cls:'primary',glyph:'plus'}),button('Open in Studio',async()=>{
    status(error);
    const r=await prepare();
    if(!el.isConnected||view!=='radar')return;
    if(r.item)await openStudio(r.item.id);else await openExternal(r);
   },{...options,glyph:'edit'}));
  }else{
   const add=button('Add',null,{glyph:'plus'});
   add.disabled=true;
   add.title='An individual audio file is required to add this sound';
   detail.append(node('small','Source link · no importable audio file found','availability'));
   actions.append(add,button('Find audio',()=>{
    document.dispatchEvent(new CustomEvent('mimic:radar-search',{detail:{
     query:[row.artist,row.title].filter(Boolean).join(' '),category,
    }}));
   },{glyph:'search'}));
  }
  actions.append(link('Open source ↗',row.url));
  el.append(badge,detail,actions,error);
  return card;
 }

 function render(data,category){
  by('radarTitle').textContent=data.title;
  const date=data.day?.split('-').reverse().join('.');
  const count=data.rows.length;
  const coverage=data.days===1?'Current snapshot'
   : data.days===7?'7-day top chart'
   : 'Top chart from available snapshots over 7 days';
  by('radarScope').textContent=data.chart
   ? data.days?[coverage,'Snapshot days: '+data.days+' of 7',date&&'Updated '+date].filter(Boolean).join(' · '):'Regional chart'
   : 'Past-week web search · country included in query · sorted by relevance';
  by('radarSourceLink').replaceChildren(link(data.chart?'Chart data ↗':'Open platform ↗',data.source_url));
  heading.hidden=false;
  status('radarStatus',[
   data.warning,data.stale?'Showing cached results.':'',
   !count&&!data.warning?(data.chart?'The chart is empty.':'No matching public videos or sound pages. Try another country or platform.'):'',
  ].filter(Boolean).join(' '),Boolean(data.warning&&!count));
  clearCards();
  if(data.playable_chart&&count){
   selection={rows:data.rows.filter(row=>row.source_id),category,index:0,shown:0,failed:0,denied:0,lastError:'',limit:data.limit,
              notice:[data.warning,data.stale?'Showing cached results.':''].filter(Boolean).join(' ')};
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
  status('radarStatus','Refreshing results…');
  try{
   const data=await runJob('radar',{category:kind,region:region.value,source:source.value,force},job=>{
    if(job.status==='running')status('radarStatus',job.message||'Refreshing results…');
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
