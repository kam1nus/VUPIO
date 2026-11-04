'use strict';
let openSettings;
(() => {
 let selected='audio',jobsTimer=false,jobSignature='',modelSignature='',devices=[],pairTimer,latestSettings;
 function selectOptions(id,values,value){const el=by(id);el.replaceChildren(...values.map(d=>new Option(d.name,d.id)));if(values.some(d=>d.id===value))el.value=String(value);el.disabled=!values.length;}
 async function refreshDevices(){
  const s=await api('settings');latestSettings=s;devices=s.devices||[];
  selectOptions('inputDevice',s.physicalInputs||[],audio.input);selectOptions('output',devices,audio.output);
  selectOptions('monitorDevice',devices.filter(d=>!d.virtual&&!/(blackhole|mimic microphone|aggregate|multi-output)/i.test(d.name)&&![1986622068,1735554416].includes(d.transport)),audio.monitorDevice);
  by('networkStatus').textContent=s.bind==='127.0.0.1'?'Доступен только на этом компьютере. Подключите его к локальной сети для пульта.':(s.tls?'HTTPS':'HTTP')+' · '+s.bind+':'+s.port;
  by('dataPath').textContent=s.data_dir;
 }
 openSettings=tab=>{
  selected=tab||selected;
  if(view!=='settings'){show('settings');return;}
  document.querySelectorAll('[data-settings]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.settings===selected)));
  document.querySelectorAll('.settingsPage').forEach(p=>p.hidden=p.id.toLowerCase()!=='settings'+selected);
  status('settingsStatus',audio.error||'',Boolean(audio.error));
  if(['audio','network','advanced','diagnostics'].includes(selected))refreshDevices().catch(e=>status('settingsStatus',e.message,true));
 };
 by('settingsNav').onclick=e=>{const b=e.target.closest('[data-settings]');if(b)openSettings(b.dataset.settings);};
 document.addEventListener('mimic:view',e=>{if(e.detail==='settings')openSettings();if(e.detail==='remote')refreshRemotes().catch(err=>status('pairNotice',err.message,true));});
 bind('jobBadge',()=>openSettings('jobs'));bind('openDiagnostics',()=>openSettings('diagnostics'));bind('goRemote',()=>show('remote'));
 function audioUi(s){
  by('micChip').textContent=s.mic?'Включён':s.permissionPending?'Ожидает доступа':'Выключен';
  by('micToggle').textContent=s.mic||s.micRequested?'Выключить микрофон':'Включить микрофон';
  const permission=['macOS ещё не запрашивала доступ','доступ ограничен','доступ закрыт в macOS','доступ разрешён'][s.micPermission];
  by('micStatus').textContent=[permission,s.notice].filter(Boolean).join(' · ');
  by('driverStatus').textContent=s.error?s.error:s.driverRegistered?(s.virtualConnected?'MIMIC Microphone подключён.':(s.outputUID==='MIMICAudioDevice_UID'?'MIMIC Microphone выбран. Выход откроется при воспроизведении.':'Драйвер виден. Выберите MIMIC Microphone в списке выходов.')):'Драйвер не зарегистрирован. Откройте «Дополнительно» для установки.';
  if(s.platform==='windows'){
   by('driverStatus').textContent=s.driverRegistered?'В Discord выберите CABLE Output, в VUPIO — CABLE Input.':'Для звука в Discord установите VB-CABLE и перезапустите VUPIO.';
   for(const id of ['physicalTest','physicalTestStop','probe','macDriverPanel'])by(id).hidden=true;
   by('physicalTestStatus').textContent='В Windows используйте проверку микрофона в Discord.';
  }
  if(document.activeElement!==by('micGain'))by('micGain').value=s.micGain??.7;
  by('micPercent').textContent=Math.round((s.micGain??.7)*100)+'%';
  for(const id of ['monitor','polyphony'])by(id).checked=Boolean(s[id]);
  by('probe').textContent=s.probeRunning?'Остановить проверку входа':'Проверить виртуальный вход';
  for(const [name,key,active] of [['physical','physicalMicLevel',s.mic],['mixer','mixerOutputLevel',s.running],['virtual','virtualMicLevel',s.virtualMeterAvailable]]){
   const level=s[key]||0,db=20*Math.log10(Math.max(1e-6,level));
   by(name+'Meter').value=active?Math.min(1,Math.max(0,(db+72)/72)):0;
   by(name+'DB').textContent=active?(level>1e-6?db.toFixed(1)+' dBFS':'−∞ dBFS'):'Неактивен';
  }
  if(s.platform!=='windows')by('physicalTestStatus').textContent=s.diagnosticActive?(s.diagnosticReady?'Скажите несколько слов. Проверка длится 10 секунд и не записывает речь.':'Ожидаем разрешение macOS и запуск входа.'):s.physicalDiagnostic&&Object.keys(s.physicalDiagnostic).length?'Проверка завершена. Откройте отчёт ниже.':'Проверка не запущена.';
  by('physicalTestResult').textContent=Object.keys(s.physicalDiagnostic||{}).length?JSON.stringify(s.physicalDiagnostic,null,2):'Отчёт появится после проверки.';
  const fields=['captureProcess','captureFormat','physicalFrames','pushedMicFrames','micConsumedFrames','micUnderruns','captureError','probeFrames','probeRMS','audioLog'];
  by('diagnosticLog').textContent=JSON.stringify(Object.fromEntries(fields.filter(k=>s[k]!==undefined).map(k=>[k,s[k]])),null,2);
 }
 document.addEventListener('mimic:audio',e=>{if(role==='admin')audioUi(e.detail);});
 function settingButton(id,fn){bind(id,async()=>{status('settingsStatus');await fn();},'settingsStatus');}
 settingButton('refreshDevices',refreshDevices);
 settingButton('restartAudio',async()=>{stopPreview();await api('audio/restart',{});await sync();await refreshDevices();notify('Аудиодвижок перезапущен. Голос выключен.');});
 settingButton('applyInput',async()=>{if(!by('inputDevice').value)throw Error('Выберите физический микрофон');await api('audio/input',{device:Number(by('inputDevice').value)});await sync();notify('Вход выбран');});
 settingButton('applyOutput',async()=>{if(!by('output').value)throw Error('Выберите аудиовыход');await api('output',{device:Number(by('output').value)});await sync();notify('Выход применён');});
 settingButton('micToggle',async()=>{
  const enabled=!audio.mic&&!audio.micRequested;
  const r=await api('mic',{enabled,device:Number(by('inputDevice').value)||undefined,gain:Number(by('micGain').value)});
  await sync();if(r.notice)status('settingsStatus',r.notice);
 });
 let gainTimer;by('micGain').oninput=()=>{const gain=Number(by('micGain').value);by('micPercent').textContent=Math.round(gain*100)+'%';clearTimeout(gainTimer);gainTimer=setTimeout(()=>api('mixer',{gain}).catch(e=>status('settingsStatus',e.message,true)),100);};
 for(const name of ['monitor','polyphony','monitorDevice'])by(name).onchange=async()=>{
  const data=name==='polyphony'?{polyphony:by(name).checked}:{monitor:by('monitor').checked,monitorDevice:Number(by('monitorDevice').value)};
  try{await api('mixer',data);}catch(e){status('settingsStatus',e.message,true);}finally{await sync().catch(()=>{});}
 };
 settingButton('physicalTest',async()=>{const s=await api('audio/mic-test',{device:Number(by('inputDevice').value)||audio.input||0,gain:Number(by('micGain').value)});if(s.notice)status('settingsStatus',s.notice);await sync();});
 settingButton('physicalTestStop',async()=>{await api('audio/mic-test-stop',{});await sync();});
 settingButton('audioTest',async()=>{stopPreview();await api('audio/test',{});await sync();});
 settingButton('probe',async()=>{
  if(audio.probeRunning){await api('audio/probe',{enabled:false});await sync();return;}
  const r=await api('audio/probe',{enabled:true});
  if(!r.probeRunning){status('settingsStatus',r.notice||'Вход пока не готов. Проверьте разрешение macOS.');return;}
  try{
   await api('audio/test',{});await pause(1300);
   const sample=await api('audio');status('settingsStatus',sample.probeFrames>0?'Получено блоков аудио: '+sample.probeFrames+' кадров · RMS '+Number(sample.probeRMS||0).toFixed(5):'Сигнал не получен. Проверьте выбранный выход и доступ к микрофону.',!sample.probeFrames);
  }finally{await api('audio/probe',{enabled:false});await sync();}
 });
 async function refreshRemotes(){
  const list=await api('remotes'),target=by('remoteDevices');target.replaceChildren();
  if(!list.length)target.append(node('p','Пока нет подключённых пультов.','muted'));
  for(const r of list){
   const el=node('div',undefined,'deviceRow'),label=node('div');
   label.append(node('strong',r.name),node('small','Доступ до '+new Date(r.expiry*1000).toLocaleDateString('ru-RU')));
   el.append(label,button('Отключить',async()=>{if(!confirm('Отключить «'+r.name+'»?'))return;await api('remotes/revoke',{id:r.id});await refreshRemotes();notify('Пульт отключён');}));target.append(el);
  }
  by('revoke').disabled=!list.length&&!audio.mic&&!audio.playing;
 }
 bind('refreshRemotes',refreshRemotes,'pairNotice');
 bind('newPair',async()=>{
  const s=await api('pair/new',{});by('pairInfo').hidden=false;by('pairCode').textContent=s.code.slice(0,4)+' '+s.code.slice(4);
  by('qr').src='/api/qr?t='+Date.now();by('qr').hidden=false;by('pairURL').textContent=s.url;by('pairURL').href=s.url;
  status('pairNotice',s.url.includes('127.0.0.1')?'Mac доступен только локально. Проверьте подключение к Wi-Fi.':'',s.url.includes('127.0.0.1'));
  clearInterval(pairTimer);
  const update=()=>{const n=Math.max(0,Math.ceil(s.expires-Date.now()/1000));by('pairExpiry').textContent=n?'Действует ещё '+fmt(n):'Код истёк. Создайте новый.';if(!n){clearInterval(pairTimer);by('pairCode').textContent='—';by('qr').hidden=true;}};
  update();pairTimer=setInterval(update,1000);
 },'pairNotice');
 bind('revoke',async()=>{if(!confirm('Отключить все пульты, звук и микрофон?'))return;await api('revoke',{});by('pairInfo').hidden=true;clearInterval(pairTimer);await sync();await refreshRemotes();notify('Все пульты отключены');},'pairNotice');
 async function updateJobs(){
  if(jobsTimer||role!=='admin')return;jobsTimer=true;
  try{
   const s=await api('ai/status'),active=s.jobs.filter(j=>['queued','running'].includes(j.status)).length;
   by('jobBadge').hidden=!active;by('jobBadge').lastChild.textContent='Задачи · '+active;
   const jobKey=JSON.stringify(s.jobs);
   if(jobKey!==jobSignature){jobSignature=jobKey;by('jobRows').replaceChildren(...(s.jobs.length?s.jobs.map(jobCard):[node('p','Задач пока нет.','muted')]));}
   const modelKey=JSON.stringify(s.models);
   if(modelKey!==modelSignature){
    modelSignature=modelKey;by('modelRows').replaceChildren(...s.models.map(m=>{
     const row=node('div',undefined,'deviceRow'),text=node('div');
     text.append(node('strong',m.title),node('small',Math.round(m.size/1e6)+' МБ · '+(m.installed?'Готова':'Не загружена')),link('Лицензия ↗',m.license_url));
     const add=button(m.installed?'Готова':'Загрузить',async()=>{await runJob('model',{model:m.id});notify('Модель готова');});add.disabled=m.installed;
     row.append(text,add);return row;
    }));
   }
   by('indexedStatus').textContent='Проиндексировано звуков: '+s.indexed;
   by('webMode').textContent=s.web_search?.has_key?'Используется ключ Tavily, сохранённый на Mac.':'Веб-поиск без ключа. Действуют лимиты сервиса.';
   document.dispatchEvent(new CustomEvent('mimic:jobs',{detail:s}));
  }catch(e){if(view==='settings'&&['models','jobs'].includes(selected))status('settingsStatus',e.message,true);}
  finally{jobsTimer=false;}
 }
 setInterval(updateJobs,1600);
 settingButton('compactModel',async()=>{openSettings('jobs');await runJob('model',{model:'language'});notify('Компактная модель готова');});
 settingButton('indexAll',async()=>{openSettings('jobs');await runJob('index_all');notify('Аудиоиндекс готов');});
 settingButton('unloadModels',async()=>{await api('ai/unload',{});notify('Модели выгружены из памяти');});
 settingButton('saveKey',async()=>{if(!by('tavilyKey').value)throw Error('Введите ключ Tavily');await api('ai/web-settings',{tavily_key:by('tavilyKey').value});by('tavilyKey').value='';notify('Ключ сохранён на Mac');await updateJobs();});
 settingButton('clearKey',async()=>{await api('ai/web-settings',{tavily_key:''});by('tavilyKey').value='';notify('Включён поиск без ключа');await updateJobs();});
 for(const id of ['installDriver','uninstallDriver','importModel'])settingButton(id,()=>window.webkit.messageHandlers.mimicNative.postMessage(id));
 by('checkUpdates').onclick=()=>{
  by('checkUpdates').disabled=true;
  status('updateStatus','Проверяем обновления…');
  window.webkit.messageHandlers.mimicNative.postMessage('checkUpdates');
 };
 window.vupioUpdateStatus=(message,error,busy)=>{
  by('checkUpdates').disabled=busy;
  status('updateStatus',message,error);
 };
 window.mimicNativeError=message=>status('settingsStatus',message,true);
 window.mimicImportModel=async (path,title)=>{try{openSettings('jobs');await runJob('model_import',{path,title});notify('Модель импортирована');}catch(e){status('settingsStatus',e.message,true);}};
})();
