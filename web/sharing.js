'use strict';
(()=>{
 const SITE='https://vupio-soundboard.denserat4.chatgpt.site';
 let overview=null,snapshot=null,busy=false,jobId=null,selected=new Set(),publishSelection=new Set(),loadedBoardChoices='';
 const target='sharingStatus';
 function collectionLink(kind,id){return SITE+(kind==='board'?'/shared/':'/drop/')+id;}
 async function copyLink(url){try{await navigator.clipboard.writeText(url);notify('Collection link copied');}catch{by('sharingLink').value=url;notify('Copy the link from the collection field');}}
 function choices(){
  const key=JSON.stringify(soundboards.map(b=>[b.id,b.title,b.clips]));if(key===loadedBoardChoices)return;loadedBoardChoices=key;
  const select=by('sharingLocalBoard'),previous=select.value;select.replaceChildren();
  for(const b of soundboards){const option=node('option',b.title+' · '+b.clips.length+' sounds');option.value=b.id;select.append(option);}
  if(soundboards.some(b=>b.id===(previous||activeBoard)))select.value=previous||activeBoard;
  if(!soundboards.length){const o=node('option','Create a board in Soundboard first');o.value='';select.append(o);}
  by('sharingTitle').value=soundboards.find(b=>b.id===select.value)?.title||'';picker();
 }
 function picker(){
  const board=soundboards.find(b=>b.id===by('sharingLocalBoard').value),drop=by('sharingKind').value==='drop';
  const rows=(board?.clips||[]).map(id=>items.find(i=>i.id===id)).filter(Boolean);publishSelection=new Set(rows.slice(0,12).map(i=>i.id));
  by('sharingSoundPicker').hidden=!drop;by('sharingSoundPicker').replaceChildren();
  by('sharingSelectionNote').textContent=drop?'Choose up to 12 sounds for this drop.':'All sounds on this board will be shared (up to 24).';
  for(const item of rows){const label=node('label',undefined,'check'),input=node('input');input.type='checkbox';input.checked=publishSelection.has(item.id);input.addEventListener('change',()=>{if(input.checked)publishSelection.add(item.id);else publishSelection.delete(item.id);});label.append(input,node('span',item.title+' · '+fmt(item.duration)));by('sharingSoundPicker').append(label);}
 }
 function controls(){
  for(const id of ['sharingRefresh','sharingPublishButton','sharingPull','sharingPush','sharingAnotherCopy','sharingConfirmPull'])by(id).disabled=busy;
  by('sharingCancel').hidden=!busy||!jobId;
  by('sharingPublishButton').disabled=busy||overview?.can_publish===false;
  by('sharingPush').disabled=busy||overview?.can_publish===false||snapshot?.local_link?.revision!==snapshot?.revision;
  by('sharingLocalBoard').disabled=busy;by('sharingKind').disabled=busy;
  by('sharingOpenForm').querySelector('button').disabled=busy;
  by('sharingMemberForm').querySelector('button').disabled=busy;
 }
 async function load(){
  choices();
  try{overview=await api('sharing/overview');by('sharingCloudStatus').textContent=(overview.can_publish?'Pro · publishing enabled':'Free · invited boards and drop imports available')+' · Shared storage '+(overview.storage.used/1048576).toFixed(1)+' / '+(overview.storage.limit/1048576)+' MB';drawLists();}
  catch(error){by('sharingCloudStatus').textContent=error.message+' Public Sound Drop links can still be imported.';}
  controls();
 }
 function drawLists(){
  for(const [kind,rows,id] of [['board',overview?.boards||[],'sharingBoards'],['drop',overview?.drops||[],'sharingDrops']]){
   const list=by(id);list.replaceChildren();
   if(!rows.length)list.append(node('p',kind==='board'?'Publish a board or ask a friend to invite your account.':'Publish your first drop from a local board.','muted'));
   for(const row of rows){
    const card=node('article',undefined,'panel stack');card.append(node('strong',row.title),node('small',kind==='board'?row.role+' · version '+row.revision+(row.archived?' · archived':''):(row.revoked?'Link disabled':'Unlisted link')));
    const actions=node('div',undefined,'row wrap');
    if(!row.revoked)actions.append(button('Review',()=>open(kind,row.id),{target}));
    if(!row.revoked&&!row.archived)actions.append(button('Copy link',()=>copyLink(collectionLink(kind,row.id)),{target,cls:'quiet'}));
    if(kind==='drop')actions.append(button(row.revoked?'Restore link':'Disable link',async()=>{await api('sharing/revoke-drop',{id:row.id,revoked:!row.revoked});if(!row.revoked&&snapshot?.kind==='drop'&&snapshot.id===row.id){snapshot=null;by('sharingSnapshot').hidden=true;}await load();},{target,cls:'quiet'}));
    else if(row.role==='owner')actions.append(button(row.archived?'Restore board':'Archive',async()=>{await api('sharing/archive',{id:row.id,archived:!row.archived});await load();if(snapshot?.id===row.id)await open(kind,row.id);},{target,cls:'quiet'}));
    card.append(actions);list.append(card);
   }
  }
 }
 async function open(kind,id){if(busy)return;const value=await api('sharing/'+kind+'/'+id);setSnapshot({...value,kind});}
 function setSnapshot(data){snapshot=data;selected=new Set(data.manifest.map(c=>c.id));by('sharingConflict').hidden=true;drawSnapshot();}
 function localBoard(){return snapshot?.local_link&&soundboards.find(b=>b.id===snapshot.local_link.board);}
 function drawSnapshot(){
  const data=snapshot;by('sharingSnapshot').hidden=!data;if(!data)return;
  const local=localBoard();by('sharingSnapshotTitle').textContent=data.title;
  by('sharingSnapshotInfo').textContent=data.kind==='board'?'Private board · '+data.role+' · version '+data.revision:'Sound Drop · '+data.manifest.length+' sounds · unlisted';
  by('sharingSnapshotDescription').textContent=data.description||'';
  by('sharingOpenLocal').hidden=!local;by('sharingPull').textContent=data.kind==='board'?(local?'Pull latest version':'Import board'):'Import selected as board';
  by('sharingPush').hidden=data.kind!=='board'||!local||!['owner','editor'].includes(data.role)||Boolean(data.archived);
  by('sharingAnotherCopy').hidden=data.kind!=='drop';
  by('sharingMemberForm').hidden=data.kind!=='board'||data.role!=='owner';
  by('sharingSyncNote').textContent=data.kind==='board'?'Cloud version '+data.revision+' · local version '+(data.local_link?.revision||'not imported')+'. Pull downloads the cloud version. Push sends your local changes. Pull newer versions before pushing.':'Preview and select the sounds to import. No audio is added until you choose Import.';
  const clips=by('sharingClips');clips.replaceChildren();
  for(const row of data.manifest){
   const card=node('div',undefined,'sharingClip');const label=node('label',undefined,'check');
   if(data.kind==='drop'){const check=node('input');check.type='checkbox';check.checked=selected.has(row.id);check.disabled=busy;check.setAttribute('aria-label','Import '+row.title);check.addEventListener('change',()=>{if(check.checked)selected.add(row.id);else selected.delete(row.id);});label.append(check);}
   label.append(node('span',row.title));card.append(label,node('small',row.category+' · '+fmt(row.duration)));
   const previewButton=button('Preview',async()=>{const version=previewVersion,result=await task('share_preview',{mode:data.kind,id:data.id,asset_id:row.id});if(view==='sharing'&&snapshot?.id===data.id&&version===previewVersion)await playPreview(result.preview_url,result.title);},{target,glyph:'play'});previewButton.disabled=busy;card.append(previewButton);clips.append(card);
  }
  const members=by('sharingMembers');members.replaceChildren();
  for(const member of data.members||[]){const row=node('div',undefined,'split wrap');row.append(node('span',member.email+' · '+member.role),button('Remove access',async()=>{await api('sharing/members',{id:data.id,email:member.email,role:'remove'});await open('board',data.id);},{target,cls:'quiet'}));members.append(row);}
  controls();
 }
 async function task(kind,body){
  if(busy)throw Error('Wait for the current sharing task.');busy=true;jobId=null;by('sharingProgress').hidden=false;drawSnapshot();controls();
  try{return await runJob(kind,body,j=>{jobId=j.id;by('sharingProgress').value=j.progress||0;status(target,j.error||j.message||'Preparing…',j.status==='failed');controls();},350);}
  finally{busy=false;jobId=null;by('sharingProgress').hidden=true;drawSnapshot();controls();}
 }
 async function pull(overwrite=false,newCopy=false){
  try{const data=snapshot,result=await task('share_pull',{mode:data.kind,id:data.id,ids:data.kind==='drop'?[...selected]:undefined,overwrite,new_copy:newCopy});await sync();chooseSoundboard(result.board_id);show('soundboard');notify('Shared collection imported · '+result.count+' sounds');}
  catch(error){if(error.code==='local_changes')by('sharingConflict').hidden=false;throw error;}
 }
 bind('openSharing',()=>{show('sharing');});bind('sharingBack',()=>show('soundboard'));bind('sharingAccount',()=>show('account'));
 bind('sharingCleanup',async()=>{const result=await api('sharing/cleanup',{});await load();status(target,'Unused uploads removed: '+result.removed);},target);
 bind('sharingRefresh',load,target);bind('sharingCancel',()=>jobId&&api('ai/cancel',{job_id:jobId}),target);
 bind('sharingCopyLink',()=>copyLink(collectionLink(snapshot.kind,snapshot.id)),target);
 bind('sharingPull',()=>pull(),target);bind('sharingConfirmPull',()=>pull(true),target);bind('sharingKeepLocal',()=>{by('sharingConflict').hidden=true;});
 bind('sharingAnotherCopy',()=>pull(false,true),target);bind('sharingOpenLocal',()=>{chooseSoundboard(localBoard()?.id||'');show('soundboard');});
 bind('sharingPush',async()=>{const data=snapshot,board=localBoard();if(!board)throw Error('Pull the shared board first.');await task('share_publish',{mode:'board',cloud_id:data.id,revision:data.revision,board_id:board.id,title:board.title,description:data.description});await sync();await open('board',data.id);await load();notify('Local changes pushed');},target);
 by('sharingLocalBoard').addEventListener('change',()=>{by('sharingTitle').value=soundboards.find(b=>b.id===by('sharingLocalBoard').value)?.title||'';picker();});by('sharingKind').addEventListener('change',picker);
 by('sharingOpenForm').addEventListener('submit',async e=>{e.preventDefault();if(busy)return;try{const value=await api('sharing/resolve',{link:by('sharingLink').value});setSnapshot(value);status(target);}catch(error){status(target,error.message,true);}});
 by('sharingPublishForm').addEventListener('submit',async e=>{
  e.preventDefault();if(busy)return;
  try{const mode=by('sharingKind').value;if(mode==='drop'&&(!publishSelection.size||publishSelection.size>12))throw Error('Select 1–12 sounds.');const result=await task('share_publish',{mode,board_id:by('sharingLocalBoard').value,ids:mode==='drop'?[...publishSelection]:undefined,title:by('sharingTitle').value,description:by('sharingDescription').value});await sync();await load();await open(mode,result.id);by('sharingLink').value=result.url;status(target,'Published. Copy the link to share it.');}
  catch(error){status(target,error.message,true);}
 });
 by('sharingMemberForm').addEventListener('submit',async e=>{e.preventDefault();if(busy)return;try{await api('sharing/members',{id:snapshot.id,email:by('sharingEmail').value.trim(),role:by('sharingMemberRole').value});by('sharingEmail').value='';await open('board',snapshot.id);status(target,'Invitation saved. Send this board link to your friend.');}catch(error){status(target,error.message,true);}});
 document.addEventListener('mimic:view',e=>{if(e.detail==='sharing'){load().catch(error=>status(target,error.message,true));}});
})();
