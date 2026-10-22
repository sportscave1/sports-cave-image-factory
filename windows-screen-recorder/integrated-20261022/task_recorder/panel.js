 'use strict';
const $=id=>document.getElementById(id),base='/api/task-recorder/';
let devices=[],device=null,state={},selected=sessionStorage.getItem('recorder-selected')||'',after='',lastSeq=-1,stopped=false,transportOK=true;
let pollRunning=false,pollAbort=null,compactLevel=1;
let stepEditor=null,editorLoading=false;
const rowCache=new Map();
const requests=new Set();
let pending=new Map(),deleted=new Set(),renames=new Map(),rowErrors=new Map(),editing='',editName='',confirmDelete='',details=null,values={},detailRequest=0,tableSignature='',attentionKey='';
const activeModes=new Set(['recording','recording_paused','running','pausing','paused','starting']);
const uuid=()=>crypto.randomUUID();
const tasks=()=> (state.tasks||[]).filter(t=>!deleted.has(t.id)).map(t=>renames.has(t.id)?{...t,name:renames.get(t.id)}:t);
const active=()=>activeModes.has(state.mode)||!!device?.active_run||!!device?.needs_review;
const starting=()=>[...pending.values()].some(c=>['record','open-popup','play','record-replacement'].includes(c.kind));
const online=()=>!!device?.connected&&transportOK;
const modern=()=>state.protocol>=2;
const desktopCapable=()=>state.desktop_capabilities?.format==='sports-cave.desktop'&&state.desktop_capabilities?.version===1&&state.desktop_capabilities?.action_versions?.includes(2);
const desktopTask=t=>t?.format==='sports-cave.desktop';
function error(text){$('error').textContent=text||'';$('error').hidden=!text;}
function notice(text){$('notice').textContent=text||'';$('notice').hidden=!text;}
function button(text,label,fn,disabled=false){const b=document.createElement('button');b.type='button';b.textContent=text;b.title=b.ariaLabel=label;b.disabled=disabled;b.onclick=e=>{e.stopPropagation();fn();};return b;}
async function api(path,data,signal){
 const controller=new AbortController();requests.add(controller);
 const abort=()=>controller.abort();signal?.addEventListener('abort',abort,{once:true});
 const timer=setTimeout(abort,50000);
 try{
  const response=await fetch(base+path,{method:data===undefined?'GET':'POST',credentials:'same-origin',headers:data===undefined?{}:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data),signal:controller.signal});
  const result=await response.json();if(!response.ok){if(result.step_errors)stepEditor?.showErrors(result.step_errors);const failure=Error(result.error||'Connection unavailable. Refresh the connection and try again.');failure.rejected=response.status>=400&&response.status<500;throw failure;}return result;
 }catch(e){if(controller.signal.aborted&&!signal?.aborted)throw Error('The connection timed out. Check the browser and use Stop before trying again.');throw e;}
 finally{clearTimeout(timer);requests.delete(controller);signal?.removeEventListener('abort',abort);}

}
function remember(){sessionStorage.setItem('recorder-commands',JSON.stringify([...pending.values()]));}
function update(result){
 compactLevel=result.compact===2?2:1;
 const oldDevice=device?.id,keepActive=active();
 // Compact responses omit only an unchanged device snapshot. Keep metadata
 // fresh (including offline/revoked state) without clearing its recordings.
 let resync=false;
 const nextDevices=result.devices.map(d=>{
  const previous=devices.find(p=>p.id===d.id);
  if(d.state_delta){
   if(!previous?.state||previous.seq!==d.state_delta.base_seq){resync=true;return d;}
   const rows=new Map((previous.state.tasks||[]).map(t=>[t.id,t]));
   for(const id of d.state_delta.tasks.remove)rows.delete(id);
   for(const task of d.state_delta.tasks.upsert)rows.set(task.id,task);
   return {...d,state:{...previous.state,...d.state_delta.changes,tasks:[...rows.values()].sort((a,b)=>a.name.toLowerCase()<b.name.toLowerCase()?-1:a.name.toLowerCase()>b.name.toLowerCase()?1:a.id.localeCompare(b.id))}};
  }
  return !d.state&&previous?.seq===d.seq?{...d,state:previous.state}:d;
 });
 if(resync){after="";return;}
 const current=nextDevices.find(d=>d.id===oldDevice);
 const next=current&&(current.connected||keepActive)?current:nextDevices.find(d=>d.connected)||current||nextDevices[0]||null;
 if(next?.id===oldDevice&&next&&next.seq<lastSeq)return;
 if(next&&!next.state){devices=nextDevices;device=next;state={};selected="";details=null;values={};after="";lastSeq=-1;transportOK=true;render();return;}
 if(next?.id!==oldDevice)lastSeq=-1;
 devices=nextDevices;device=next;
 if(device){lastSeq=device.seq;state=device.state||{};after=String(device.seq);}else{state={};after='';lastSeq=-1;}
 transportOK=true;
 for(const t of state.tasks||[])if(renames.get(t.id)===t.name)renames.delete(t.id);
 if(selected&&!tasks().some(t=>t.id===selected)){selected='';details=null;values={};}
 if(!selected&&!active()&&state.selected_id&&tasks().some(t=>t.id===state.selected_id))selected=state.selected_id;
 sessionStorage.setItem('recorder-selected',selected);render();
}
async function confirmCommand(command,result){
 const deadline=Date.now()+45000;
 for(let n=0;Date.now()<deadline&&['queued','dispatched'].includes(result.status)&&!stopped;n++){
  // The server waits for a helper update. Back off on old servers that ignore
  // wait=1; this remains one receipt request at a time, with the same command ID.
  const started=Date.now();
  result=await api('receipt?device='+encodeURIComponent(command.device_id)+'&id='+command.id+'&wait=1');
  if(['queued','dispatched'].includes(result.status)&&Date.now()-started<250)await new Promise(r=>setTimeout(r,Math.min(2000,350*(n+1))));
 }
 if(result.status!=='applied'){
  if(command.kind==='edit-copy'&&result.receipt?.step_errors)stepEditor?.showErrors(result.receipt.step_errors);
  throw Error(result.receipt?.message||'This control is not confirmed. Check the browser and use Stop before trying again.');
 }
 const receipt=result.receipt||{};
 if(command.kind==='delete'){
  deleted.add(command.payload.id);if(selected===command.payload.id){selected='';details=null;values={};}
  if(confirmDelete===command.payload.id)confirmDelete='';notice('Recording deleted.');
 }
 if(command.kind==='rename'){renames.set(command.payload.id,receipt.name||command.payload.name);editing='';notice('Recording renamed.');}
 if(['record','open-popup'].includes(command.kind)){selected='';details=null;values={};if(desktopCapable())notice(receipt.message||'Choose your prepared window on the Windows toolbar.');}
 if(command.kind==='repair-copy'){selected=receipt.new_task_id;details=null;values={};notice('Corrected copy saved. Original preserved. Review it, then press Play.');}
 if(command.kind==='edit-copy'){selected=receipt.new_task_id;details=null;values={};notice('Edited copy saved. Original preserved. Press Play when ready.');}
 if(receipt.tasks)state={...state,tasks:receipt.tasks};
 // The receipt is durable; read the helper's acknowledged snapshot rather than
 // guessing a mode from button clicks. A stale in-flight poll cannot undo it.
 update(await api(compactLevel===2&&device?'state?compact=2&device='+encodeURIComponent(device.id)+'&after='+device.seq+'&wait=0':'state'));
 if(['record','open-popup'].includes(command.kind)&&state.active_task_id)selected=state.active_task_id;
 return receipt;
}
async function send(kind,payload={}){
 const taskId=payload.id;
 if(device&&!device.state){error('Loading this PC’s recordings. Wait a moment, then try again.');return null;}
 if(!online()){error('PC is offline. Start Task Recorder from the Windows Start menu, then refresh the connection.');return null;}
 if(!modern()&&!['stop','stop-save','view'].includes(kind)){error('Update the PC helper using Settings, then try again.');return null;}
 if([...pending.values()].some(c=>c.kind===kind&&c.payload.id===taskId))return null;
 const reopen=kind==='open-popup'&&desktopCapable()&&state.desktop_capabilities?.popup_reopen;
 if(['record','open-popup','play','record-replacement'].includes(kind)&&(starting()||active()&&!reopen))return null;
 if(stepEditor&&['record','play','reusable','rename','delete','repair-copy'].includes(kind)){error('Save or cancel the edit first.');return null;}
 const command={device_id:device.id,id:uuid(),kind,payload};
 let dispatched=false;
 pending.set(command.id,command);remember();error('');notice('');render();
 try{
  const result=await api('command',command);dispatched=true;
  const receipt=await confirmCommand(command,result);
  pending.delete(command.id);remember();if(taskId)rowErrors.delete(taskId);return receipt;
 }catch(e){
  // Retain uncertain command identity for navigation/reconnect reconciliation;
  // never submit a fresh duplicate start automatically.
  if(e.rejected&&!dispatched)pending.delete(command.id);
  else if(!stopped){try{const r=await api('receipt?device='+command.device_id+'&id='+command.id);if(!['queued','dispatched'].includes(r.status))pending.delete(command.id);}catch{}}
  error(e.message);if(taskId)rowErrors.set(taskId,e.message);return null;
 }finally{remember();after='';render();}
}
async function reconcile(){
 let saved=[];try{saved=JSON.parse(sessionStorage.getItem('recorder-commands')||'[]');}catch{}
 for(const command of saved){
  if(command.device_id!==device?.id)continue;
  pending.set(command.id,command);render();
  try{await confirmCommand(command,await api('receipt?device='+command.device_id+'&id='+command.id));}
  catch(e){error(e.message);}finally{pending.delete(command.id);remember();render();}
 }
}
function status(){
 if(device?.connected&&transportOK&&!device.state)return 'Loading recordings…';
 if(!online())return 'PC offline · Start the Windows helper';
 if(device?.needs_review)return state.message||'Interrupted · Review the recorder, then Stop';
 const mode=state.mode||'idle';
 if([...pending.values()].some(c=>c.kind==='pause'))return 'Pausing…';
 if([...pending.values()].some(c=>['stop','stop-save'].includes(c.kind)))return 'Stopping…';
 if(starting())return 'Starting…';
 if(mode==='starting')return state.message||'Starting…';
 if(mode==='running')return state.message?.startsWith('Step ')?state.message:`Playing · ${state.step} of ${state.total}`;
 if(mode==='pausing')return 'Pausing… The current action is finishing.';
 if(mode==='recording')return 'Recording · Stop to save';
 if(mode==='recording_paused')return state.message||'Recording paused';
 if(mode==='paused')return state.message||'Paused';
 if(!active()&&tasks().find(t=>t.id===selected)?.issue_count)return 'Needs attention · Review the flagged step below';
 if(!active()&&tasks().find(t=>t.id===selected)?.result==='interrupted')return 'Needs review · Previous action is unconfirmed';
 if(['completed','stopped'].includes(mode)&&state.active_task_id&&selected!==state.active_task_id){
  const result=tasks().find(t=>t.id===selected)?.result;
  return {completed:'Completed',stopped:'Stopped',interrupted:'Needs review'}[result]||'Ready';
 }
 if(mode==='completed')return 'Completed';
 if(mode==='stopped')return state.message||'Stopped';
 if(mode==='interrupted')return state.message||'Interrupted. Review the recorder, then Stop.';
 return 'Ready';
}
function renderControls(){
 const mode=state.mode||'idle',busy=active()||starting(),enabled=online(),capable=modern();
 const task=tasks().find(t=>t.id===selected);
 $('record').disabled=!enabled||!capable||!desktopCapable()||busy||!!stepEditor||editorLoading;
 $('record').title=desktopCapable()?'Record in your existing Windows applications':'Update required: install the Windows recorder helper.';
 $('name').disabled=$('website').disabled=busy;
 $('view').disabled=!enabled||!device?.state;
 $('play').hidden=busy;$('play').disabled=!enabled||!capable||!task||!!stepEditor||editorLoading||(desktopTask(task)&&(!desktopCapable()||!task.playback_available));
 $('view').hidden=false;
 const legacy=task&&!desktopTask(task),nativeTask=tasks().find(t=>t.id===state.active_task_id);
 const nativeBusy=desktopCapable()&&(busy||mode==='interrupted')&&(desktopTask(nativeTask)||!nativeTask);
 $('activity').hidden=!nativeBusy;
 $('popupStatus').textContent={recording:'Recording',recording_paused:'Paused',running:'Playing',paused:'Paused',starting:'Ready to play',interrupted:'Review draft'}[mode]||'Windows popup';
 $('popupMessage').textContent=state.message||'Continue in the Windows popup.';
 const stoppedRecovery=!!device?.needs_review&&['idle','stopped','completed'].includes(mode);
 $('acknowledgeStop').hidden=!stoppedRecovery;
 $('acknowledgeStop').disabled=!enabled||[...pending.values()].some(c=>c.kind==='stop');
 if(stoppedRecovery){$('popupStatus').textContent='Previous session needs review';$('popupMessage').textContent='The previous connection was interrupted. Check the application’s result, then acknowledge Stop to enable playback. Saved recordings are preserved.';}
 $('openPopup').disabled=!enabled||!state.desktop_capabilities?.popup_reopen||starting();
 $('openPopup').title=state.desktop_capabilities?.popup_reopen?'Return to the current recording or playback':'Update the Windows helper to reopen an active popup.';
 $('record').hidden=nativeBusy;
 $('toolbar').hidden=!legacy&&!(busy&&nativeTask&&!desktopTask(nativeTask));
 if(busy&&nativeTask&&!desktopTask(nativeTask)){$('advanced').open=true;$('legacyTools').open=true;}
 $('pause').hidden=!['running','recording'].includes(mode);
 $('resume').hidden=!(mode==='recording_paused'||mode==='paused'&&state.can_resume);
 $('stop').hidden=!busy&&mode!=='interrupted';
 for(const k of ['pause','resume','stop'])$(k).disabled=!enabled||[...pending.values()].some(c=>c.kind===k);
 const request=[...pending.values()].find(c=>['record','open-popup','play','record-replacement'].includes(c.kind));
 const requestName=request?.kind==='record'?(request.payload.name||'New recording'):tasks().find(t=>t.id===request?.payload.id)?.name;
 $('activeName').textContent=starting()&&(mode==='starting'||!activeModes.has(mode))?(requestName||'Starting task'):busy?(state.active_task_name||requestName||'Current task'):(task?.name||'Select a recording');
 $('message').textContent=status();
 $('startup').checked=!!state.startup;$('startup').disabled=!enabled||!capable;
 $('revoke').disabled=!device;$('outdated').hidden=!device||!device.state||(state.protocol>=3&&(!desktopTask(task)||desktopCapable()));
}
function date(value){return value?new Date(value).toLocaleString(undefined,{dateStyle:'short',timeStyle:'short'}):'—';}
function duration(value){if(!Number.isFinite(value)||value<0)return '—';const secs=Math.floor(value/1000);return String(Math.floor(secs/60)).padStart(2,'0')+':'+String(secs%60).padStart(2,'0');}
function select(id){$('inputs').replaceChildren();selected=id;sessionStorage.setItem('recorder-selected',id);details=null;values={};notice('');render();const t=tasks().find(t=>t.id===id);if(t?.inputs?.length)inspect(id);}
async function inspect(id){
 const request=++detailRequest;const result=await send('inspect',{id});
 if(result&&selected===id&&request===detailRequest){details=result;values={...result.values};renderInputs();}
}
async function editRecording(id){
 if(desktopTask(tasks().find(t=>t.id===id))){error('Desktop recordings are immutable. Record another task from the Windows toolbar.');return;}
 if(active()||starting()||stepEditor||editorLoading)return;
 if(state.protocol<4){error('Editing needs the updated PC helper (version 4). Existing recordings and playback are unchanged.');return;}
 editorLoading=true;renderControls();
 try{
  const module=await import('/task-recorder/assets/editor.js');
  const result=await send('inspect',{id});if(!result||active()||starting())return;
  stepEditor=module.createEditor($('stepEditor'),{
   task:result.task,revision:result.revision,values:result.values,send,
   canEdit:()=>online()&&!active()&&!starting()&&![...pending.values()].some(c=>['edit-copy','edit-file'].includes(c.kind)),isRecording:()=>state.recording||state.mode==='recording_paused',
   changed:fit,close:()=>{stepEditor=null;$('stepEditor').hidden=true;$('stepEditor').replaceChildren();document.body.classList.remove('editing-steps');render();}
  });
  document.body.classList.add('editing-steps');render();$('stepEditor').scrollIntoView({block:'start'});
 }catch(e){error(e.message);}finally{editorLoading=false;renderControls();}
}
async function play(id){
 const t=tasks().find(t=>t.id===id);if(!t)return;
 if(desktopTask(t)&&(!desktopCapable()||!t.playback_available)){error('Update required, or this early desktop draft needs a new scoped recording.');return;}
 if(t.attention?.length){review(id);return;}
 // Exact playback uses local defaults; selecting a row does not retarget an
 // existing run. Pause/Stop are always device/run controls, not selection controls.
 const supplied=selected===id?{...values}:{};
 selected=id;sessionStorage.setItem('recorder-selected',id);details=null;values=supplied;render();
 await send('play',{id,revision:t.revision,values:supplied});
}
function renderInputs(){
 $('inputs').replaceChildren();if(!details||details.task.id!==selected)return;
 for(const input of details.task.inputs||[]){
  const label=document.createElement('label');label.textContent=input.name.replaceAll('_',' ');
  const field=document.createElement('input');field.value=values[input.name]||'';field.ariaLabel=label.textContent;
  field.oninput=()=>values[input.name]=field.value;label.append(field);$('inputs').append(label);
 }
}
function renderTable(){
 const rows=tasks().filter(t=>!desktopTask(t)||t.revision),mode=state.mode||'idle';
 const sig=JSON.stringify([rows,selected,mode,state.active_task_id,active(),online(),modern(),state.desktop_capabilities?.library_management,[...pending.values()].map(c=>[c.kind,c.payload.id]),editing,confirmDelete,[...rowErrors]]);
 if(sig===tableSignature)return;tableSignature=sig;
 const focused=document.activeElement,focusId=focused?.dataset?.editId,start=focused?.selectionStart,end=focused?.selectionEnd;
 const seen=new Set(),positions={recordings:0,legacyRecordings:0};$('empty').hidden=rows.some(desktopTask);
 rows.forEach(t=>{
  seen.add(t.id);const native=desktopTask(t),table=$(native?'recordings':'legacyRecordings'),index=positions[table.id]++;
  const isActive=active()&&state.active_task_id===t.id,busy=active()||starting();
  const signature=JSON.stringify([t,t.id===selected,isActive,mode,busy,online(),modern(),state.desktop_capabilities?.library_management,editing===t.id,editing===t.id?editName:'',confirmDelete===t.id,rowErrors.get(t.id)]);
  const cached=rowCache.get(t.id);
  if(cached?.signature===signature){if(table.children[index]!==cached.node)table.insertBefore(cached.node,table.children[index]||null);return;}
  const tr=document.createElement('tr');tr.dataset.taskId=t.id;tr.classList.toggle('selected',t.id===selected);tr.setAttribute('aria-selected',String(t.id===selected));
  const cells=Array.from({length:4},()=>{const td=document.createElement('td');tr.append(td);return td;});
  if(editing===t.id){
   const form=document.createElement('form');form.className='rename';const field=document.createElement('input');field.value=editName;field.maxLength=100;field.ariaLabel='New name for '+t.name;field.dataset.editId=t.id;field.oninput=()=>editName=field.value;
   const save=button('Save','Save name for '+t.name,()=>send('rename',{id:t.id,name:editName}),!online()||busy);
   form.onsubmit=e=>{e.preventDefault();if(!save.disabled)send('rename',{id:t.id,name:editName});};form.append(field,save,button('Cancel','Cancel rename',()=>{editing='';renderTable();}));cells[0].append(form);
  }else{const label=button(t.name,'Select '+t.name,()=>select(t.id));label.className='row-name';cells[0].append(label);}
  cells[1].textContent=date(t.updated_at);
  cells[2].textContent=isActive?({running:'Playing',paused:'Paused',recording:'Recording',recording_paused:'Paused'}[mode]||'Starting…'):({completed:'Completed',stopped:'Stopped',interrupted:'Needs review',executing:'Needs review',running:'Needs review',paused:'Paused'}[t.result]||'Saved');
  if(!isActive&&t.attention?.length){cells[2].replaceChildren(button('Needs attention','Review '+t.name,()=>review(t.id)));}
  const actions=document.createElement('div');actions.className='actions';
  const unavailable=native&&(!desktopCapable()||!t.playback_available);
  actions.append(button('Play','Play '+t.name,()=>play(t.id),!online()||!modern()||busy||unavailable));
  const menu=document.createElement('details');menu.className='row-menu';
  const summary=document.createElement('summary');summary.textContent='⋯';summary.setAttribute('aria-label','More options for '+t.name);menu.append(summary);
  const tools=document.createElement('div');tools.className='menu-tools';
  const mutable=!native||state.desktop_capabilities?.library_management===true;
  const rename=button('Rename','Rename '+t.name,()=>{editing=t.id;editName=t.name;confirmDelete='';renderTable();const field=[...document.querySelectorAll('input')].find(e=>e.dataset.editId===t.id);field?.focus();field?.select();},!mutable||busy||!online());
  const edit=button(native?'Edit actions (read-only)':'Edit','Edit '+t.name,()=>editRecording(t.id),native||busy||!online());
  edit.title=native?'Recorded actions are protected. Make a new recording to change the steps.':'';
  const remove=button('Delete','Delete '+t.name,()=>{confirmDelete=t.id;editing='';renderTable();},!mutable||busy||!online());
  if(!mutable){rename.title=remove.title='Update the Windows helper to manage this recording.';}
  tools.append(rename,edit,remove);menu.append(tools);actions.append(menu);cells[3].append(actions);
  if(confirmDelete===t.id){const confirm=document.createElement('div');confirm.className='confirm';confirm.append(document.createTextNode(native?'Remove this recording from the library? ':'Delete this recording? '),button('Delete','Confirm delete '+t.name,()=>send('delete',{id:t.id}),!online()||busy),button('Cancel','Cancel delete',()=>{confirmDelete='';renderTable();}));cells[3].append(confirm);}
  if(rowErrors.has(t.id)){const error=document.createElement('span');error.className='row-error';error.setAttribute('role','alert');error.textContent=rowErrors.get(t.id);cells[3].append(error);}
  if(cached?.node.parentNode===table)cached.node.replaceWith(tr);else table.insertBefore(tr,table.children[index]||null);
  rowCache.set(t.id,{signature,node:tr});
 });
 for(const [id,cached] of rowCache)if(!seen.has(id)){cached.node.remove();rowCache.delete(id);}
 if(focusId){const field=[...document.querySelectorAll('input')].find(e=>e.dataset.editId===focusId);if(field){field.focus();field.setSelectionRange(start,end);}}
}
function render(){
 if(!details||details.task.id!==selected)$('inputs').replaceChildren();
 $('pc').textContent=device?device.name+' · '+(online()?'Connected':'Helper unavailable')+(state.runtime?' · '+state.runtime.build+' / IPC '+state.runtime.ipc+' / '+(state.runtime.native_sha256||'').slice(0,8):''):'No PC connected';
 let pages=$('libraryPages');if(!pages){pages=document.createElement('div');pages.id='libraryPages';$('pc').after(pages);}
 pages.replaceChildren();if(state.library_page){const p=state.library_page;pages.append(button('Previous recordings','Previous recordings',()=>send('library-page',{offset:Math.max(0,p.offset-20)}),!online()||p.offset===0));pages.append(document.createTextNode(` ${p.total ? p.offset+1 : 0}–${Math.min(p.total,p.offset+tasks().filter(t=>t.revision).length)} of ${p.total} `));pages.append(button('Next recordings','Next recordings',()=>send('library-page',{offset:p.next}),!online()||p.next===null));}
 let adapterStatus=$('adapterStatus');if(!adapterStatus){adapterStatus=document.createElement('div');adapterStatus.id='adapterStatus';$('pc').after(adapterStatus);}adapterStatus.textContent=state.runtime?.adapter?.explanation||'';
 $('setup').hidden=online();$('setupText').textContent=!transportOK?'Connection unavailable. Check your internet connection, then refresh.':device?'The Windows recorder is unavailable. Open Task Recorder from the Windows Start menu, then refresh the connection.':'Connect this Windows PC to use the recorder popup. You only need to do this once.';
 $('pair').hidden=!!device;
 $('legacySummary').textContent='Older browser recordings ('+tasks().filter(t=>!desktopTask(t)).length+')';
 $('seen').textContent=device?'Last seen '+date(device.last_seen*1000):'';
 $('selectedSettings').hidden=!selected||desktopTask(tasks().find(t=>t.id===selected));$('selectedName').textContent=tasks().find(t=>t.id===selected)?.name||'';
 $('reusable').disabled=!online()||!modern()||active()||starting();
 renderControls();renderTable();renderAttention();stepEditor?.refresh();fit();
}
function review(id){$('advanced').open=true;$('legacyTools').open=true;select(id);renderAttention();$('attention').scrollIntoView({block:'nearest'});}
function renderAttention(){
 const task=tasks().find(t=>t.id===selected),issue=task?.attention?.[0];
 $('attention').hidden=!issue||desktopTask(task);if(!issue||desktopTask(task))return;
 $('attentionHeading').textContent='Needs attention · Step '+issue.step+(issue.kind==='interrupted'?' · Interrupted recording':'');
 $('attentionReason').textContent=issue.explanation||issue.reason;
 $('recordedReason').textContent=issue.explanation!==issue.reason?'Recorded reason: '+issue.reason:'';
 const key=task.id+task.revision;if(key!==attentionKey){attentionKey=key;$('correctionValue').value='';}
 const correctable=!['prerequisite','target'].includes(issue.kind);
 $('correctionKind').disabled=$('correctionValue').disabled=!correctable;
 $('repairCopy').disabled=!correctable||!online()||state.protocol<3||active()||[...pending.values()].some(c=>c.kind==='repair-copy');
 $('repairCopy').title=correctable?'':'Use Edit to supply the exact source reference or record the missing actions. A wait cannot reconstruct them.';
 $('recordReplacement').disabled=active();
}
$('correctionKind').onchange=()=>{
 const nav=$('correctionKind').value==='navigate';$('correctionLabel').textContent=nav?'Website address':'Visible text to wait for';
 $('correctionValue').placeholder=nav?'https://example.com':'A unique heading or label on the intended page';
};
$('repairCopy').onclick=async()=>{
 const task=tasks().find(t=>t.id===selected),issue=task?.attention?.[0];if(!issue)return;
 if(!$('correctionValue').value.trim())return error('Enter the website or visible text needed for this step. The original will be preserved.');
 await send('repair-copy',{id:task.id,revision:task.revision,step:issue.step,replacement:{action:$('correctionKind').value,value:$('correctionValue').value.trim()}});
};
$('recordReplacement').onclick=()=>send(state.desktop_capabilities?.popup_reopen?'open-popup':'record',{});
function stop(){return send(state.recording||state.mode==='recording_paused'?'stop-save':'stop');}
function pollDelay(ms){
 return new Promise(resolve=>{
  const finish=()=>{clearTimeout(timer);document.removeEventListener('visibilitychange',finish);window.removeEventListener('pageshow',finish);resolve();};
  const timer=setTimeout(finish,ms);document.addEventListener('visibilitychange',finish);window.addEventListener('pageshow',finish);
 });
}
async function poll(){
 if(pollRunning)return;pollRunning=true;
 let reconciled=false,failures=0;
 try{while(!stopped){
  // Returning to the page reconciles the real helper state. Hiding the page
  // never pauses/stops a run; command receipts continue independently.
  if(document.hidden){await pollDelay(60000);continue;}
  try{
   pollAbort=new AbortController();
   const result=await api('state'+(device?'?compact='+compactLevel+'&device='+encodeURIComponent(device.id)+(after?'&after='+after:''):''),undefined,pollAbort.signal);
   if($('error').textContent==='Connection unavailable. Check your internet connection and refresh.')error('');
   update(result);failures=0;if(device&&!reconciled){reconciled=true;reconcile();}
   if(!device)await pollDelay(5000);
  }catch(e){
   if(stopped)break;if(pollAbort?.signal.aborted)continue;
   transportOK=false;render();
   await pollDelay(Math.min(30000,(1600+800*Math.random())*2**Math.min(failures++,4)));
  }finally{pollAbort=null;}
 }}finally{pollRunning=false;}
}
$('record').onclick=()=>send(state.desktop_capabilities?.popup_reopen?'open-popup':'record',{});
$('openPopup').onclick=()=>send('open-popup',{});
$('acknowledgeStop').onclick=()=>send('stop');
$('play').onclick=()=>play(selected);$('pause').onclick=()=>send('pause');$('resume').onclick=()=>send('resume');$('stop').onclick=stop;$('view').onclick=()=>send('view');
$('reusable').onclick=async()=>{if(!selected)return;const id=selected;if(await send('reusable',{id}))await inspect(id);};
$('startup').onchange=()=>send('startup',{enabled:$('startup').checked});
$('revoke').onclick=async()=>{if(!device)return;try{await api('revoke',{device_id:device.id});device=null;state={};after='';lastSeq=-1;error('');render();}catch(e){error(e.message);}};
$('pair').onclick=async()=>{try{const data=await api('pairing',{});$('challenge').hidden=false;$('code').textContent=data.code;$('approve').href='http://127.0.0.1:18931/pair#'+new URLSearchParams({origin:location.origin,code:data.code}).toString();error('');fit();}catch(e){error(e.message);}};
$('refresh').onclick=()=>{after='';pollAbort?.abort();document.dispatchEvent(new Event('visibilitychange'));};
// Fit the same-origin OS frame to content: the OS owns vertical scrolling.
let frame=null,fitQueued=false;
try{if(window.parent!==window&&window.parent.location.origin===location.origin)frame=window.frameElement;}catch{}
function fit(){if(!frame||fitQueued)return;fitQueued=true;requestAnimationFrame(()=>{fitQueued=false;frame.style.height=Math.ceil(document.querySelector('main').offsetHeight+2)+'px';});}
if(frame){new ResizeObserver(fit).observe(document.querySelector('main'));window.parent.addEventListener('resize',fit);}
document.addEventListener('click',e=>{for(const menu of document.querySelectorAll('.row-menu[open]'))if(!menu.contains(e.target))menu.open=false;});
document.addEventListener('keydown',e=>{if(e.key==='Escape')for(const menu of document.querySelectorAll('.row-menu[open]')){menu.open=false;menu.querySelector('summary').focus();}});
document.addEventListener('visibilitychange',()=>{if(document.hidden)pollAbort?.abort();});
window.addEventListener('pageshow',()=>{stopped=false;after='';if(frame)window.parent.addEventListener('resize',fit);poll();});
window.addEventListener('pagehide',()=>{stopped=true;for(const request of requests)request.abort();if(frame)window.parent.removeEventListener('resize',fit);});
poll();
