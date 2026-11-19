'use strict';
let soundboards=[],activeBoard='';
try{activeBoard=localStorage.getItem('vupio:selected-board')||'';}catch{}
let remoteBoardOptions='';
let boardDraft=null, boardSelection=new Set(), boardInitial=new Set(), boardSaving=false;
function currentSoundboard(){return soundboards.find(board=>board.id===activeBoard);}
function boardLibraryItems(){
 const board=currentSoundboard();if(!board)return items;
 const lookup=new Map(items.map(item=>[item.id,item]));
 return board.clips.map(id=>lookup.get(id)).filter(Boolean).sort((a,b)=>Number(Boolean(b.favorite))-Number(Boolean(a.favorite)));
}
function scrollToActiveBoard(){[...by('boardTabs').children].find(tab=>tab.dataset.board===activeBoard)?.scrollIntoView({block:'nearest',inline:'nearest'});}
function saveBoardChoice(){try{localStorage.setItem('vupio:selected-board',activeBoard);}catch{}}
function chooseSoundboard(id){
 if(id&&!soundboards.some(board=>board.id===id))id='';
 activeBoard=id;saveBoardChoice();page=0;activeCategory='';
 libraryOptions();renderSoundboardTabs();renderLibrary();scrollToActiveBoard();
}
function applySoundboards(boards){
 soundboards=boards;
 if(activeBoard&&!soundboards.some(board=>board.id===activeBoard)){activeBoard='';saveBoardChoice();page=0;}
 renderSoundboardTabs();
}
function renderSoundboardTabs(){
 const list=by('boardTabs'),scroll=list.scrollLeft,focusID=document.activeElement?.closest('#boardTabs button')?.dataset.board;
 list.replaceChildren();
 for(const board of [{id:'',title:'All sounds',clips:items},...soundboards]){
  const tab=button('',()=>chooseSoundboard(board.id),{cls:'boardTab',label:board.title});
  tab.dataset.board=board.id;tab.setAttribute('aria-pressed',String(activeBoard===board.id));
  tab.append(node('span',board.title),node('small',String(board.clips.length)));
  list.append(tab);
 }
 list.scrollLeft=scroll;
 if(focusID!==undefined)[...list.children].find(tab=>tab.dataset.board===focusID)?.focus({preventScroll:true});
 const signature=JSON.stringify(soundboards.map(board=>[board.id,board.title]));
 if(remoteBoardOptions!==signature){by('remoteBoardChoice').replaceChildren(new Option('All sounds',''),...soundboards.map(board=>new Option(board.title,board.id)));remoteBoardOptions=signature;}
 by('remoteBoardChoice').value=activeBoard;
 by('manageBoard').hidden=!activeBoard;
 renderImportBoardHint();
}
function renderImportBoardHint(){
 const current=currentSoundboard();
 by('importBoardHint').textContent=current?'Adding new sounds to '+current.title+' · Switch boards in Soundboard':'';
 by('importBoardHint').hidden=!current||!['discover','radar','studio'].includes(view);
}
async function addImportedSound(item,destination=activeBoard){
 if(!destination||!item?.id)return;
 try{await api('boards/members',{id:destination,add:[item.id]});}
 catch(error){throw Error('Sound saved to All sounds, but could not be added to this board. '+error.message);}
}
function openBoardManager(board=null){
 boardDraft=board?{id:board.id,title:board.title}:null;
 boardInitial=new Set(board?.clips||[]);boardSelection=new Set(boardInitial);
 by('boardDialogTitle').textContent=board?'Manage board':'Create a soundboard';
 by('boardName').value=board?.title||'';by('boardSoundSearch').value='';
 by('deleteBoard').hidden=!board;by('saveBoard').textContent=board?'Save changes':'Create board';
 by('boardDeleteConfirm').hidden=true;
 status('boardStatus');renderBoardPicker();by('boardEditor').showModal();by('boardName').focus();
}
function filteredBoardPicker(){
 const query=by('boardSoundSearch').value.trim().toLocaleLowerCase();
 return items.filter(item=>!query||[item.title,item.tags,item.category].join(' ').toLocaleLowerCase().includes(query));
}
function renderBoardPicker(){
 const matches=filteredBoardPicker(),list=by('boardSoundList');list.replaceChildren();
 by('boardSelectionCount').textContent=boardSelection.size+' selected';
 by('selectBoardMatches').disabled=!matches.length||boardSaving;
 for(const item of matches){
  const row=node('label',undefined,'boardPickerRow check');
  const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.checked=boardSelection.has(item.id);checkbox.disabled=boardSaving;
  checkbox.addEventListener('change',()=>{
   if(checkbox.checked)boardSelection.add(item.id);else boardSelection.delete(item.id);
   by('boardSelectionCount').textContent=boardSelection.size+' selected';
  });
  const text=node('span',undefined,'boardPickerText');text.append(node('strong',item.title),node('small',categoryLabel(item.category)+' · '+fmt(item.duration)));
  row.append(checkbox,text);list.append(row);
 }
 if(!matches.length)list.append(node('p',items.length?'No sounds match your search.':'Your library is empty. Create the board, then add audio or find a meme.','muted boardPickerEmpty'));
}
bind('newBoard',()=>openBoardManager());
bind('manageBoard',()=>openBoardManager(currentSoundboard()));
by('remoteBoardChoice').addEventListener('change',e=>chooseSoundboard(e.target.value));
by('boardSoundSearch').addEventListener('input',renderBoardPicker);
by('boardName').addEventListener('input',()=>status('boardStatus'));
by('closeBoardEditor').addEventListener('click',()=>{if(!boardSaving)by('boardEditor').close();});
by('boardEditor').addEventListener('cancel',e=>{if(boardSaving)e.preventDefault();});
bind('selectBoardMatches',()=>{for(const item of filteredBoardPicker())boardSelection.add(item.id);renderBoardPicker();});
by('boardForm').addEventListener('submit',async e=>{
 e.preventDefault();if(boardSaving)return;
 const title=by('boardName').value.trim();if(!title){status('boardStatus','Enter a board name.',true);return;}
 setBoardBusy(true);status('boardStatus','Saving…');
 try{
  const result=await api('boards/save',{id:boardDraft?.id||null,title,
   add:[...boardSelection].filter(id=>!boardInitial.has(id)),remove:[...boardInitial].filter(id=>!boardSelection.has(id))});
  activeBoard=result.id;saveBoardChoice();page=0;activeCategory='';
  if(syncing)await syncing.catch(()=>{});await sync();
  scrollToActiveBoard();by('boardEditor').close();notify(boardDraft?'Board updated':'Board created');
 }catch(error){status('boardStatus',error.message,true);}
 finally{setBoardBusy(false);}
});
function setBoardBusy(value){
 boardSaving=value;
 for(const id of ['saveBoard','deleteBoard','closeBoardEditor','boardName','cancelDeleteBoard','confirmDeleteBoard'])by(id).disabled=value;
 renderBoardPicker();
}
bind('deleteBoard',()=>{
 if(!boardDraft||boardSaving)return;
 by('boardDeleteMessage').textContent='Delete “'+boardDraft.title+'”?';
 by('boardDeleteConfirm').hidden=false;by('confirmDeleteBoard').focus();
});
bind('cancelDeleteBoard',()=>{by('boardDeleteConfirm').hidden=true;by('deleteBoard').focus();});
bind('confirmDeleteBoard',async()=>{
 const draft=boardDraft;if(!draft||boardSaving)return;
 setBoardBusy(true);status('boardStatus','Deleting board…');
 try{
  await api('boards/delete',{id:draft.id});
  if(activeBoard===draft.id){activeBoard='';saveBoardChoice();page=0;}
  if(syncing)await syncing.catch(()=>{});await sync();by('boardEditor').close();notify('Board deleted. Your sounds are kept.');
 }finally{setBoardBusy(false);}
},'boardStatus');

document.addEventListener('mimic:library',()=>{
 if(!by('boardEditor').open||boardSaving)return;
 const available=new Set(items.map(item=>item.id));
 boardSelection=new Set([...boardSelection].filter(id=>available.has(id)));
 renderBoardPicker();
});
