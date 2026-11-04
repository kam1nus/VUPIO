'use strict';
let openStudio,openExternal;
(() => {
 const c=by('wave'),ctx=c.getContext('2d'),container=by('waveContainer');
 let source=null,draft=null,undo='',segmentList=[],initial=null,peaks=[],duration=0,start=0,end=0,sourceToken=0;
 let drag=null,selectionPlayback=false,raf=0,busy=false;
 const tone=getComputedStyle(document.documentElement),accent=tone.getPropertyValue('--accent').trim(),muted=tone.getPropertyValue('--muted').trim();
 const ms=x=>Math.round(x*1000)/1000;
 const clamp=(x,a,b)=>Math.min(Math.max(x,a),b);
 const bounds=()=>({start:ms(start),end:Math.min(duration,ms(end)),silence:by('silence').checked,normalize:by('normalize').checked,fade_in:Number(by('fadeIn').value),fade_out:Number(by('fadeOut').value)});
 function draw(){
  if(!source||by('studio').hidden)return;
  const w=c.clientWidth,h=c.clientHeight,dpr=window.devicePixelRatio||1;if(!w||!h)return;
  if(c.width!==Math.round(w*dpr)||c.height!==Math.round(h*dpr)){c.width=Math.round(w*dpr);c.height=Math.round(h*dpr);}
  ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
  if(!peaks.length||!duration)return;
  const a=start/duration*w,b=end/duration*w;
  ctx.fillStyle='rgba(184,238,119,.10)';ctx.fillRect(a,0,b-a,h);
  ctx.strokeStyle='#454b54';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(0,h/2);ctx.lineTo(w,h/2);ctx.stroke();
  const scale=.43*h/Math.max(.12,...peaks.map(p=>Math.max(Math.abs(p[0]),Math.abs(p[1]))));
  for(let i=0;i<peaks.length;i++){
   const x=(i+.5)*w/peaks.length,[lo,hi]=peaks[i];
   ctx.fillStyle=x>=a&&x<=b?accent:muted;ctx.globalAlpha=x>=a&&x<=b?.9:.42;
   ctx.fillRect(x,h/2-hi*scale,Math.max(1,w/peaks.length*.64),Math.max(1,(hi-lo)*scale));
  }
  ctx.globalAlpha=1;ctx.fillStyle=accent;
  for(const x of [a,b]){ctx.fillRect(clamp(x-1,0,w-2),0,2,h);ctx.fillRect(clamp(x-4,0,w-8),3,8,12);}
  if(selectionPlayback&&preview.currentTime>0){const x=preview.currentTime/duration*w;ctx.fillStyle='#fff';ctx.fillRect(x,0,1,h);}
 }
 new ResizeObserver(draw).observe(container);
 function setBounds(a,b){
  const gap=Math.min(.01,duration);start=clamp(Number(a)||0,0,Math.max(0,duration-gap));end=clamp(Number(b)||duration,start+gap,duration);
  for(const id of ['trimStart','trimEnd','trimStartRange','trimEndRange','trimDuration'])by(id).max=duration;
  by('trimStart').value=ms(start);by('trimEnd').value=ms(end);by('trimDuration').value=ms(end-start);
  by('trimStartRange').value=start;by('trimEndRange').value=end;
  by('selectionLength').textContent=fmt(start,true)+' — '+fmt(end,true)+' · '+(end-start).toFixed(2)+' с';
  draw();
 }
 function ruler(){by('ruler').replaceChildren(...Array.from({length:5},(_,i)=>node('span',fmt(duration*i/4,true))));}
 function invalidate(){by('draftStatus').textContent='Изменения применятся при предпрослушивании или сохранении.';}
 function moveBound(id,value){
  if(!source||!Number.isFinite(value))return;
  if(id.startsWith('trimStart'))setBounds(Math.min(value,end-Math.min(.01,duration)),end);
  else if(id==='trimDuration')setBounds(start,start+Math.max(.01,value));
  else setBounds(start,value);
  invalidate();
 }
 for(const id of ['trimStart','trimEnd','trimDuration','trimStartRange','trimEndRange']){
  const el=by(id);el.addEventListener(el.type==='range'?'input':'change',()=>moveBound(id,el.valueAsNumber));
 }
 for(const id of ['silence','normalize','fadeIn','fadeOut'])by(id).addEventListener('change',invalidate);
 function fromPointer(e){const rect=c.getBoundingClientRect();return clamp((e.clientX-rect.left)/rect.width,0,1)*duration;}
 c.addEventListener('pointerdown',e=>{
  if(!source||!peaks.length)return;
  const t=fromPointer(e);drag={t,a:start,b:end,mode:Math.min(Math.abs(t-start),Math.abs(t-end))<duration*.055?(Math.abs(t-start)<Math.abs(t-end)?'start':'end'):'range'};
  c.setPointerCapture(e.pointerId);
 });
 c.addEventListener('pointermove',e=>{
  if(!drag)return;const t=fromPointer(e);
  if(drag.mode==='range')setBounds(Math.min(drag.t,t),Math.max(drag.t,t));
  if(drag.mode==='start')setBounds(Math.min(t,end-Math.min(.01,duration)),end);
  if(drag.mode==='end')setBounds(start,t);invalidate();
 });
 for(const ev of ['pointerup','pointercancel','lostpointercapture'])c.addEventListener(ev,()=>drag=null);
 function options(){
  const sel=by('studioClip');sel.replaceChildren(new Option('Выбрать из библиотеки…',''),...items.map(i=>new Option(i.title,i.id)));
  sel.value=source?.itemId||'';
 }
 document.addEventListener('mimic:library',options);
 document.addEventListener('mimic:view',e=>{if(e.detail==='studio')requestAnimationFrame(draw);});
 async function removeDraft(){
  const old=draft;draft=null;
  if(old?.draft_id&&!old.saved)await api('ai/discard',{draft_id:old.draft_id});
 }
 function displaySpeech(segments){
  segmentList=segments||[];by('segments').replaceChildren();
  if(!segmentList.length){by('segments').append(node('p','Фразы пока не найдены. Запустите распознавание речи.','muted'));return;}
  for(const s of segmentList.slice(0,1000)){
   by('segments').append(button(fmt(s.start,true)+' · '+s.text,()=>{setBounds(s.start,s.end);invalidate();},{cls:'quiet'}));
  }
 }
 function applyPlan(p){
  setBounds(p.start,p.end);by('silence').checked=Boolean(p.silence);by('normalize').checked=Boolean(p.normalize);
  by('fadeIn').value=p.fade_in??0;by('fadeOut').value=p.fade_out??0;invalidate();
 }
 async function load(next,plan,segments){
  const token=++sourceToken;selectionPlayback=false;stopPreview();
  removeDraft().catch(e=>notify(e.message,true));
  source=next;peaks=[];duration=next.duration;initial=plan;
  by('studioEmpty').hidden=true;by('studioWorkspace').hidden=false;by('studioCard').hidden=!next.itemId;
  by('editorTitle').textContent=next.title;by('editorSource').textContent=next.kind==='clip'?'Исходник из библиотеки':'Исходник из интернета';
  by('copyTitle').value=(next.title+(next.itemId?' · edit':'')).slice(0,160);by('copyTags').value='';
  by('editCommand').value='';by('playhead').textContent='0:00';by('speechDetails').open=false;displaySpeech(segments);
  options();show('studio');applyPlan(plan);ruler();status('editorStatus');status('waveMessage','Загружаем волну…');
  by('draftStatus').textContent='Подготовьте предпрослушивание перед сохранением.';
  try{
   const waveform=await api('ai/wave/'+next.kind+'/'+next.id);if(token!==sourceToken)return;
   peaks=waveform.peaks;duration=Math.min(next.duration,waveform.duration);
   setBounds(start,end);ruler();status('waveMessage');draw();
  }catch(e){if(token===sourceToken)status('waveMessage',e.message,true);}
 }
 openStudio=async id=>{
  const item=items.find(i=>i.id===id);if(!item)throw Error('Звук не найден в библиотеке');
  const token=++sourceToken;
  const original=await api('ai/source/'+id);
  if(token!==sourceToken)return;
  if(original.asset_id)return openExternal(original,id);
  const next={...item,itemId:id,kind:'clip',url:'/api/file/'+id};
  await load(next,{start:0,end:item.duration,normalize:true},[]);
  if(source!==next)return;
  try{const cached=await api('ai/analysis/'+id);if(source===next)displaySpeech(cached.segments);}catch{}
 };
 openExternal=async(r,itemId)=>{
  const next={id:r.asset_id,itemId,title:r.metadata.title,duration:r.report.duration,kind:'original',url:'/api/ai/original/'+r.asset_id};
  await load(next,r.plan,r.report.analysis?.segments);
 };
 by('studioClip').onchange=e=>{if(e.target.value)openStudio(e.target.value).catch(e=>notify(e.message,true));};
 bind('studioCard',()=>{const item=items.find(i=>i.id===source?.itemId);if(item)openEditor(item);});
 bind('resetSelection',()=>{setBounds(0,duration);invalidate();status('editorStatus');});
 function animate(){
  cancelAnimationFrame(raf);
  const tick=()=>{
   if(!selectionPlayback||preview.paused){draw();return;}
   if(preview.currentTime>=end){preview.pause();preview.currentTime=start;}
   by('playhead').textContent=fmt(preview.currentTime,true);draw();
   if(!preview.paused)raf=requestAnimationFrame(tick);
  };
  raf=requestAnimationFrame(tick);
 }
 bind('editorPlay',async()=>{
  if(!source)return;
  if(!selectionPlayback||!preview.getAttribute('src')){
   preparePreview(source.url,source.title,source.kind==='clip'?source.id:null);selectionPlayback=true;
  }
  if(preview.currentTime<start||preview.currentTime>=end||preview.readyState===0)preview.currentTime=start;
  await preview.play();animate();
 },'editorStatus');
 bind('editorPause',()=>{if(selectionPlayback)preview.pause();});
 bind('editorStop',()=>{if(selectionPlayback){stopPreview();selectionPlayback=false;}by('playhead').textContent=fmt(start,true);draw();});
 preview.addEventListener('emptied',()=>{if(!preview.getAttribute('src')||preview.getAttribute('src')!==source?.url)selectionPlayback=false;draw();});
 async function work(kind,data){
  if(busy)throw Error('Дождитесь текущей операции Studio.');
  busy=true;
  try{return await runJob(kind,data,j=>{
   if(['queued','running'].includes(j.status))status('editorStatus',(j.message||jobLabels[kind])+' · '+Math.round((j.progress||0)*100)+'%');
  });}finally{busy=false;}
 }
 async function applyCommand(command){
  if(!command)throw Error('Введите команду для обработки звука.');
  const current=source,r=await work('plan',{...(current.kind==='clip'?{id:current.id}:{asset_id:current.id}),command});
  if(source!==current)return;
  applyPlan(r.plan);displaySpeech(r.segments);status('editorStatus',r.plan.warning||'');
  if(!r.plan.warning)notify('Команда применена. Проверьте выделение.');
 }
 bind('applyCommand',()=>applyCommand(by('editCommand').value.trim()),'editorStatus');
 bind('suggestMoment',()=>applyCommand('Подбери момент'),'editorStatus');
 bind('transcribe',async()=>{
  const current=source;
  const r=await work(current.kind==='clip'?'index':'asset_speech',current.kind==='clip'?{id:current.id,require_speech:true}:{asset_id:current.id});
  if(source!==current)return;
  displaySpeech(r.segments);by('speechDetails').open=true;status('editorStatus',r.segments?.length?'':'Речь не распознана. Можно задать границы вручную.');
 },'editorStatus');
 async function render(){
  const current=source,p=bounds(),key=JSON.stringify(p);
  if(draft?.key===key)return draft;
  const r=await work(current.kind==='clip'?'render':'fetch_recut',current.kind==='clip'?{id:current.id,...p}:{asset_id:current.id,...p});
  if(source!==current||JSON.stringify(bounds())!==key){
   if(r.draft_id)await api('ai/discard',{draft_id:r.draft_id});
   throw Error('Границы изменились во время обработки. Подготовьте результат снова.');
  }
  await removeDraft();draft={...r,key};
  by('draftStatus').textContent='Черновик готов. Исходный звук сохранён.';status('editorStatus');return draft;
 }
 bind('previewEdit',async()=>{const r=await render();selectionPlayback=false;await playPreview(r.preview_url,by('copyTitle').value.trim()||source.title);},'editorStatus');
 bind('discardEdit',async()=>{
  if(busy)throw Error('Дождитесь обработки или отмените её в списке задач.');
  selectionPlayback=false;stopPreview();await removeDraft();applyPlan(initial);by('copyTitle').value=(source.title+(source.itemId?' · edit':'')).slice(0,160);by('copyTags').value='';by('editCommand').value='';status('editorStatus');
  by('draftStatus').textContent='Изменения отменены.';
 },'editorStatus');
 bind('saveEdit',async()=>{
  const current=source,r=await render(),title=by('copyTitle').value.trim(),tags=by('copyTags').value.trim();
  const result=await work(current.kind==='clip'?'commit':'fetch_commit',current.kind==='clip'?{draft_id:r.draft_id,title,tags}:{asset_id:r.asset_id,title,tags,variant:true});
  r.saved=true;
  if(result.undo_draft_id){undo=result.undo_draft_id;by('undoSave').hidden=false;}
  await sync();status('editorStatus');by('draftStatus').textContent=result.duplicate?'Этот звук уже в библиотеке.':'Сохранено: '+result.item.title;
  notify(result.duplicate?'Этот звук уже в библиотеке':'Копия в Soundboard');
 },'editorStatus');
 bind('undoSave',async()=>{await api('ai/undo',{draft_id:undo});undo='';by('undoSave').hidden=true;if(draft?.saved)draft=null;await sync();by('draftStatus').textContent='Добавление отменено; исходник сохранён.';},'editorStatus');
})();
