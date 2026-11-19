'use strict';
(()=>{
 let timer, refreshing=false, opened=false;
 const target='accountStatus';
 function draw(info){
  const signed=info.state==='signed_in', pending=info.state==='pending';
  by('accountName').textContent=signed?(info.account?.display_name||info.account?.email||'Your account'):pending?'Confirm sign-in':'Your VUPIO account';
  by('accountPlan').textContent=signed?(info.membership?.plan==='pro'?'Pro · tester access':'Free'):'Not signed in';
  by('accountLogin').hidden=signed||pending;by('accountLogin').disabled=Boolean(info.busy);
  by('accountLogout').hidden=!signed&&!pending;by('accountLogout').textContent=pending?'Cancel sign-in':'Sign out';
  by('accountRefresh').disabled=Boolean(info.busy)||pending;
  by('accountPending').hidden=!pending;by('accountCode').textContent=info.user_code||'';
  const uri=info.verification_uri;
  if(uri?.startsWith('https://vupio-soundboard.denserat4.chatgpt.site/connect?code='))by('accountConfirm').href=uri;
  else by('accountConfirm').removeAttribute('href');
  by('accountRedeemPanel').hidden=!signed;
  by('accountExpiry').textContent=signed&&info.membership?.expires_at?'Tester access until '+new Date(info.membership.expires_at).toLocaleDateString():'';
  status(target,info.busy?'Connecting…':info.message||'',Boolean(info.error));
  const list=by('accountDevices');list.replaceChildren();
  for(const device of info.devices||[]){
   const row=node('div',undefined,'split');
   const description=node('div');description.append(node('strong',device.name||'VUPIO computer'),node('p',device.platform+(device.id===info.device_id?' · This computer':''),'muted'));
   row.append(description,button('Disconnect',async()=>draw(await api('account/revoke',{device_id:device.id})),{target}));list.append(row);
  }
  by('accountDevicesPanel').hidden=!signed;
 }
 async function syncAccount(){if(refreshing||view!=='account'||role!=='admin')return;refreshing=true;try{draw(await api('account/status'));}catch(e){status(target,e.message,true);}finally{refreshing=false;}}
 bind('accountLogin',async()=>{draw(await api('account/begin',{}));},target);
 bind('accountRefresh',async()=>draw(await api('account/refresh',{})),target);
 bind('accountLogout',async()=>draw(await api('account/logout',{})),target);
 by('accountRedeemForm').addEventListener('submit',async e=>{
  e.preventDefault();const submit=by('accountRedeemButton');submit.disabled=true;
  try{draw(await api('account/redeem',{code:by('accountTesterCode').value.trim()}));by('accountTesterCode').value='';}
  catch(err){status(target,err.message,true);}finally{submit.disabled=false;}
 });
 document.addEventListener('mimic:view',async e=>{
  clearInterval(timer);if(e.detail!=='account')return;
  if(!opened){opened=true;try{draw(await api('account/refresh',{}));}catch(err){status(target,err.message,true);}}
  await syncAccount();timer=setInterval(syncAccount,1500);
 });
})();
