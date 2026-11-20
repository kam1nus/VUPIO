'use strict';
let radarMode='charts';
(()=>{
 let info=null,data=null,selected=new Set(),topicId=null,busy=false,jobId=null,access=false,lastAccountRefresh=0;
 const target='proStatus';
 by('proRegion').replaceChildren(...[...by('radarRegion').options].map(o=>o.cloneNode(true)));
 const modeButtons=[...by('radarModes').querySelectorAll('button')];
 function permissions(){
  by('proAccess').textContent=access?'Pro active · personal topics and AI collections':'Pro required to generate and prepare collections. Your saved boards stay available.';
  for(const id of ['proGenerate','proNewTopic','proPrepare','proBoard'])by(id).disabled=busy||!access;
  const saved=data?.board_id&&soundboards.some(b=>b.id===data.board_id);
  by('proBoard').textContent=saved?'Open board':'Create board';
  if(saved)by('proBoard').disabled=busy;
  else by('proBoard').disabled ||= !data||!data.rows.some(r=>selected.has(r.key)&&r.ready&&!r.error)||data.rows.some(r=>selected.has(r.key)&&(!r.ready||r.error));
  by('proPrepare').disabled ||= !selected.size;
  by('proSaved').disabled=busy;modeButtons.forEach(b=>b.disabled=busy);
  by('proGenerateForm').setAttribute('aria-busy',String(busy));
  by('proCancel').hidden=!jobId||!busy;
 }
 async function load(){
  let account=await api('account/status');
  if(Date.now()-lastAccountRefresh>60000){
   lastAccountRefresh=Date.now();account=await api('account/refresh',{});
   for(let attempt=0;account.busy&&attempt<80;attempt++){await pause(250);account=await api('account/status');}
  }
  access=account.state==='signed_in'&&account.membership?.plan==='pro'&&(!account.membership.expires_at||account.membership.expires_at>Date.now());
  info=await api('ai/pro');
  drawTopics();drawSaved();permissions();
 }
 function drawSaved(){
  const select=by('proSaved');select.replaceChildren(node('option','Choose a collection…'));
  select.firstChild.value='';
  for(const row of info?.collections||[]){const o=node('option',row.title+' · '+new Date(row.created*1000).toLocaleDateString());o.value=row.id;select.append(o);}
  if(data)select.value=data.id;
 }
 function drawTopics(){
  const list=by('proTopicList');list.replaceChildren();
  if(!info?.topics.length)list.append(node('p','Save a topic to refresh a feed around your interests.','muted'));
  for(const topic of info?.topics||[]){
   const row=node('div',undefined,'topicChip');
   const open=button(topic.title,async()=>{
    topicId=topic.id;by('proBrief').value=topic.query;by('proRegion').value=topic.region;by('proCategory').value=topic.category;
    by('proFormTitle').textContent=topic.title;by('proGenerate').textContent='Refresh topic';
    by('proFormHint').textContent='Refresh to find relevant sounds. New badges compare this feed with its previous refresh.';
    if(topic.collection_id)await openCollection(topic.collection_id);else{data=null;by('proCollection').hidden=true;}
    drawTopics();
   },{target});
   open.setAttribute('aria-pressed',String(topicId===topic.id));open.disabled=busy;
   const remove=button('×',async()=>{await api('ai/pro/delete-topic',{id:topic.id});if(topicId===topic.id)resetTopic();await load();},{label:'Delete topic '+topic.title,target,cls:'quiet'});remove.disabled=busy;
   row.append(open,remove);list.append(row);
  }
 }
 function resetTopic(){topicId=null;by('proFormTitle').textContent='Build an AI collection';by('proGenerate').textContent='Generate collection';by('proFormHint').textContent='Describe a mood, a game or a moment. Review real sounds before creating a board.';}
 async function switchMode(mode){
  radarMode=mode;stopPreview();
  modeButtons.forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mode===mode)));
  by('radarCharts').hidden=mode!=='charts';by('radarRefresh').hidden=mode!=='charts';by('proPanel').hidden=mode==='charts';by('proTopics').hidden=mode!=='topics';
  document.dispatchEvent(new CustomEvent('mimic:radar-mode'));
  if(mode!=='charts'){resetTopic();await load();}
 }
 for(const b of modeButtons)bind(b,()=>switchMode(b.dataset.mode),target);
 bind('proAccount',()=>show('account'));
 bind('proNewTopic',()=>{by('proTopicForm').hidden=false;by('proTopicTitle').focus();},target);
 bind('proTopicCancel',()=>{by('proTopicForm').hidden=true;});
 by('proTopicForm').addEventListener('submit',async e=>{
  e.preventDefault();if(busy||!access)return;const submit=e.submitter;submit.disabled=true;
  try{const saved=await api('ai/pro/topic',{title:by('proTopicTitle').value,query:by('proTopicQuery').value,region:by('proRegion').value,category:by('proCategory').value});topicId=saved.id;by('proBrief').value=by('proTopicQuery').value;by('proFormTitle').textContent=by('proTopicTitle').value;by('proGenerate').textContent='Refresh topic';by('proTopicForm').hidden=true;await load();notify('Topic saved');}
  catch(error){status(target,error.message,true);}finally{submit.disabled=false;}
 });
 async function task(kind,body){
  if(busy)throw Error('Wait for the current collection task.');
  busy=true;jobId=null;by('proProgress').hidden=false;by('proProgress').value=0;draw();drawTopics();
  try{return await runJob(kind,body,j=>{
   jobId=j.id;status(target,j.error||j.message||'Starting…',j.status==='failed');by('proProgress').value=j.progress||0;permissions();
  },400);}finally{busy=false;jobId=null;by('proProgress').hidden=true;draw();drawTopics();}
 }
 bind('proCancel',()=>jobId&&api('ai/cancel',{job_id:jobId}),target);
 by('proGenerateForm').addEventListener('submit',async e=>{
  e.preventDefault();if(busy||!access)return;
  try{const result=await task('pro_generate',{brief:by('proBrief').value,topic_id:radarMode==='topics'?topicId:null,count:Number(by('proCount').value),region:by('proRegion').value,category:by('proCategory').value,local:by('proLocal').checked,web:by('proWeb').checked});setData(result);await load();status(target,result.rows.length?'Collection ready. Preview and choose the sounds you want.':'No matching sounds. Change the description or enable another source.');}
  catch(error){status(target,error.message,true);}
 });
 async function openCollection(id){setData(await api('ai/collection/'+encodeURIComponent(id)));}
 by('proSaved').addEventListener('change',()=>{if(by('proSaved').value)openCollection(by('proSaved').value).catch(e=>status(target,e.message,true));});
 function setData(value,keep=false){data=value;if(!keep)selected=new Set(value.rows.map(r=>r.key));else selected=new Set([...selected].filter(key=>value.rows.some(r=>r.key===key)));draw();}
 async function prepare(keys){const result=await task('pro_prepare',{id:data.id,keys});setData(result,true);return result;}
 function draw(){
  by('proCollection').hidden=!data;permissions();if(!data)return;
  by('proCollectionTitle').textContent=data.title;
  by('proEvidence').textContent=(data.mode==='local_ai'?'Local AI-assisted selection':'Metadata selection')+' · '+data.evidence;
  by('proNotices').hidden=!data.notices?.length;by('proNoticeList').replaceChildren(...(data.notices||[]).map(t=>node('p',t,'muted')));
  const cards=by('proCards');cards.replaceChildren();
  if(!data.rows.length)cards.append(node('p','No candidates yet. Try a more specific description.','muted'));
  for(const row of data.rows){
   const el=node('article',undefined,'panel stack proCard'),head=node('div',undefined,'split');
   const label=node('label',undefined,'check'),check=node('input');check.type='checkbox';check.checked=selected.has(row.key);check.disabled=busy;check.setAttribute('aria-label','Select '+row.title);
   check.addEventListener('change',()=>{if(check.checked)selected.add(row.key);else selected.delete(row.key);permissions();});
   label.append(check,node('strong',row.title));head.append(label);if(row.new)head.append(node('small','New to your feed','availability'));el.append(head);
   el.append(node('p',[row.source,row.duration?fmt(row.duration):'Duration after preparation'].filter(Boolean).join(' · '),'muted small'),node('p',row.reason,'muted'));
   const state=node('p',row.error||(row.ready?'Ready to preview':'Prepare to check this source'),row.error?'inlineStatus error':'availability');el.append(state);
   const actions=node('div',undefined,'row wrap');
   const previewButton=button(row.ready?'Preview':'Prepare & preview',async()=>{
    const original=data.id,key=row.key;const version=previewVersion;
    if(!row.ready)await prepare([key]);
    const current=data?.id===original&&data.rows.find(r=>r.key===key);
    if(current?.error)throw Error(current.error);
    if(current?.ready&&view==='radar'&&radarMode!=='charts'&&version===previewVersion)await playPreview(current.preview_url,current.title,current.local_id);
   },{target:state,glyph:'play'});previewButton.disabled=busy||(!access&&!row.ready);
   const edit=button('Edit',async()=>{
    if(!row.ready)await prepare([row.key]);const current=data.rows.find(r=>r.key===row.key);
    if(current?.error)throw Error(current.error);
    if(current?.local_id)await openStudio(current.local_id);else if(current?.asset_id){await openExternal({asset_id:current.asset_id,metadata:{title:current.title},report:{duration:current.full_duration||current.duration},plan:current.plan||{start:0,end:current.duration}});}
   },{target:state,glyph:'edit'});edit.disabled=busy||(!access&&!row.ready);
   const like=button('Like',async()=>{await api('ai/pro/feedback',{key:row.key,state:'like'});notify('Preference saved for future collections');},{target:state});like.disabled=busy;
   const hide=button('Hide',async()=>{await api('ai/pro/feedback',{key:row.key,state:'hide'});selected.delete(row.key);el.remove();permissions();notify('Hidden from future collections');},{target:state});hide.disabled=busy;
   const replace=button('Replace',async()=>{setData(await api('ai/pro/replace',{id:data.id,key:row.key}),true);},{target:state});replace.disabled=busy||!access||!data.pool?.length;
   actions.append(previewButton,edit,like,hide,replace);if(row.page_url)actions.append(link('Source ↗',row.page_url));el.append(actions);cards.append(el);
  }
 }
 bind('proPrepare',()=>prepare([...selected]),target);
 bind('proBoard',async()=>{
  if(data?.board_id&&soundboards.some(b=>b.id===data.board_id)){chooseSoundboard(data.board_id);show('soundboard');return;}
  const result=await task('pro_board',{id:data.id,keys:[...selected],title:data.title});await sync();chooseSoundboard(result.board_id);show('soundboard');notify('Collection saved as a soundboard');
 },target);
 document.addEventListener('mimic:view',e=>{if(e.detail==='radar'&&radarMode!=='charts')load().catch(err=>status(target,err.message,true));});
})();
