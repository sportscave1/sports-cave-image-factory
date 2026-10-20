 'use strict';
const $=id=>document.getElementById(id),base='/api/task-recorder/';
let devices=[],device=null,state={},selected=sessionStorage.getItem('recorder-selected')||'',after='',lastSeq=-1,stopped=false,transportOK=true;
let pollRunning=false,pollAbort=null,compactLevel=1;
const rowCache=new Map();
const requests=new Set();
let pending=new Map(),deleted=new Set(),renames=new Map(),rowErrors=new Map(),editing='',editName='',confirmDelete='',details=null,values={},detailRequest=0,tableSignature='',attentionKey='';
const activeModes=new Set(['recording','recording_paused','running','pausing','paused','starting']);
const uuid=()=>crypto.randomUUID();
const tasks=()=> (state.tasks||[]).filter(t=>!deleted.has(t.id)).map(t=>renames.has(t.id)?{...t,name:renames.get(t.id)}:t);
const active=()=>activeModes.has(state.mode)||!!device?.active_run||!!device?.needs_review;
const starting=()=>[...pending.values()].some(c=>['record','play'].includes(c.kind));
const online=()=>!!device?.connected&&transportOK;
const modern=()=>state.protocol>=2;
function error(text){$('error').textContent=text||'';$('error').hidden=!text;}
function notice(text){$('notice').textContent=text||'';$('notice').hidden=!text;}
function button(text,label,fn,disabled=false){const b=document.createElement('button');b.type='button';b.textContent=text;b.title=b.ariaLabel=label;b.disabled=disabled;b.onclick=e=>{e.stopPropagation();fn();};return b;}
async function api(path,data,signal){
 const controller=new AbortController();requests.add(controller);
 const abort=()=>controller.abort();signal?.addEventListener('abort',abort,{once:true});
 const timer=setTimeout(abort,50000);
 try{
  const response=await fetch(base+path,{method:data===undefined?'GET':'POST',credentials:'same-origin',headers:data===undefined?{}:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data),signal:controller.signal});
  const result=await response.json();if(!response.ok)throw Error(result.error||'Connection unavailable. Refresh the connection and try again.');return result;
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
 if(result.status!=='applied')throw Error(result.receipt?.message||'This control is not confirmed. Check the browser and use Stop before trying again.');
 const receipt=result.receipt||{};
 if(command.kind==='delete'){
  deleted.add(command.payload.id);if(selected===command.payload.id){selected='';details=null;values={};}
  if(confirmDelete===command.payload.id)confirmDelete='';notice('Recording deleted.');
 }
 if(command.kind==='rename'){renames.set(command.payload.id,receipt.name||command.payload.name);editing='';notice('Recording renamed.');}
 if(command.kind==='record'){selected='';details=null;values={};}
 if(command.kind==='repair-copy'){selected=receipt.new_task_id;details=null;values={};notice('Corrected copy saved. Original preserved. Review it, then press Play.');}
 if(receipt.tasks)state={...state,tasks:receipt.tasks};
 // The receipt is durable; read the helper's acknowledged snapshot rather than
 // guessing a mode from button clicks. A stale in-flight poll cannot undo it.
 update(await api(compactLevel===2&&device?'state?compact=2&device='+encodeURIComponent(device.id)+'&after='+device.seq+'&wait=0':'state'));
 if(command.kind==='record'&&state.active_task_id)selected=state.active_task_id;
 return receipt;
}
async function send(kind,payload={}){
 const taskId=payload.id;
 if(device&&!device.state){error('Loading this PC’s recordings. Wait a moment, then try again.');return null;}
 if(!online()){error('PC is offline. Start Task Recorder from the Windows Start menu, then refresh the connection.');return null;}
 if(!modern()&&!['stop','stop-save','view'].includes(kind)){error('Update the PC helper using Settings, then try again.');return null;}
 if([...pending.values()].some(c=>c.kind===kind&&c.payload.id===taskId))return null;
 if(['record','play'].includes(kind)&&(starting()||active()))return null;
 const command={device_id:device.id,id:uuid(),kind,payload};
 pending.set(command.id,command);remember();error('');notice('');render();
 try{
  const receipt=await confirmCommand(command,await api('command',command));
  pending.delete(command.id);remember();if(taskId)rowErrors.delete(taskId);return receipt;
 }catch(e){
  // Retain uncertain command identity for navigation/reconnect reconciliation;
  // never submit a fresh duplicate start automatically.
  if(!stopped){try{const r=await api('receipt?device='+command.device_id+'&id='+command.id);if(!['queued','dispatched'].includes(r.status))pending.delete(command.id);}catch{}}
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
 if(device?.needs_review)return 'Interrupted · Check the browser, then Stop';
 const mode=state.mode||'idle';
 if([...pending.values()].some(c=>c.kind==='pause'))return 'Pausing…';
 if([...pending.values()].some(c=>['stop','stop-save'].includes(c.kind)))return 'Stopping…';
 if(starting())return 'Starting…';
 if(mode==='running')return `Playing · ${state.step} of ${state.total}`;
 if(mode==='pausing')return 'Pausing… The current action is finishing.';
 if(mode==='recording')return 'Recording · Stop to save';
 if(mode==='recording_paused')return state.message||'Recording paused';
 if(mode==='paused')return state.message||'Paused';
 if(!active()&&tasks().find(t=>t.id===selected)?.issue_count)return 'Needs attention · Review the flagged step below';
 if(mode==='completed')return 'Completed';
 if(mode==='stopped')return state.message==='Recording saved.'?'Recording saved.':'Stopped';
 if(mode==='interrupted')return 'Interrupted. Check the browser, then Stop.';
 return 'Ready';
}
function renderControls(){
 const mode=state.mode||'idle',busy=active()||starting(),enabled=online(),capable=modern();
 const task=tasks().find(t=>t.id===selected);
 $('record').disabled=!enabled||!capable||busy;
 $('name').disabled=$('website').disabled=busy;
 $('view').disabled=!enabled||!device?.state;
 $('play').hidden=busy;$('play').disabled=!enabled||!capable||!task;
 $('pause').hidden=!['running','recording'].includes(mode);
 $('resume').hidden=!(mode==='recording_paused'||mode==='paused'&&state.can_resume);
 $('stop').hidden=!busy&&mode!=='interrupted';
 for(const k of ['pause','resume','stop'])$(k).disabled=!enabled||[...pending.values()].some(c=>c.kind===k);
 const request=[...pending.values()].find(c=>['record','play'].includes(c.kind));
 const requestName=request?.kind==='record'?(request.payload.name||'New recording'):tasks().find(t=>t.id===request?.payload.id)?.name;
 $('activeName').textContent=starting()&&(mode==='starting'||!activeModes.has(mode))?(requestName||'Starting task'):busy?(state.active_task_name||requestName||'Current task'):(task?.name||'Select a recording');
 $('message').textContent=status();
 $('startup').checked=!!state.startup;$('startup').disabled=!enabled||!capable;
 $('revoke').disabled=!device;$('outdated').hidden=!device||!device.state||state.protocol>=3;
}
function date(value){return value?new Date(value).toLocaleString(undefined,{dateStyle:'short',timeStyle:'short'}):'—';}
function duration(value){if(!Number.isFinite(value)||value<0)return '—';const secs=Math.floor(value/1000);return String(Math.floor(secs/60)).padStart(2,'0')+':'+String(secs%60).padStart(2,'0');}
function select(id){$('inputs').replaceChildren();selected=id;sessionStorage.setItem('recorder-selected',id);details=null;values={};render();const t=tasks().find(t=>t.id===id);if(t?.inputs?.length)inspect(id);}
async function inspect(id){
 const request=++detailRequest;const result=await send('inspect',{id});
 if(result&&selected===id&&request===detailRequest){details=result;values={...result.values};renderInputs();}
}
async function play(id){
 const t=tasks().find(t=>t.id===id);if(!t)return;
 if(t.attention?.length){review(id);return;}
 // Exact playback uses local defaults; selecting a row does not retarget an
 // existing run. Pause/Stop are always device/run controls, not selection controls.
 const supplied=selected===id?{...values}:{};await send('play',{id,revision:t.revision,values:supplied});
}
function renderInputs(){
 $('inputs').replaceChildren();if(!details||details.task.id!==selected)return;
 for(const input of details.task.inputs){
  const label=document.createElement('label');label.textContent=input.name.replaceAll('_',' ');
  const field=document.createElement('input');field.value=values[input.name]||'';field.ariaLabel=label.textContent;
  field.oninput=()=>values[input.name]=field.value;label.append(field);$('inputs').append(label);
 }
}
function renderTable(){
 const rows=tasks(),mode=state.mode||'idle';
 const sig=JSON.stringify([rows,selected,mode,state.active_task_id,active(),online(),modern(),[...pending.values()].map(c=>[c.kind,c.payload.id]),editing,confirmDelete,[...rowErrors]]);
 if(sig===tableSignature)return;tableSignature=sig;
 const focused=document.activeElement,focusId=focused?.dataset?.editId,start=focused?.selectionStart,end=focused?.selectionEnd;
 const table=$('recordings'),seen=new Set();$('empty').hidden=rows.length>0;
 const counts=new Map();for(const t of rows)counts.set(t.name,(counts.get(t.name)||0)+1);
 rows.forEach((t,index)=>{
  seen.add(t.id);
  const isActive=active()&&state.active_task_id===t.id;
  const rowSignature=JSON.stringify([t,t.id===selected,isActive,isActive?mode:'',active()||starting(),online(),modern(),editing===t.id,editing===t.id?editName:'',confirmDelete===t.id,rowErrors.get(t.id),counts.get(t.name)>1?index:-1,[...pending.values()].filter(c=>c.payload.id===t.id).map(c=>c.kind)]);
  const cached=rowCache.get(t.id);
  if(cached?.signature===rowSignature){if(table.children[index]!==cached.node)table.insertBefore(cached.node,table.children[index]||null);return;}
  const tr=document.createElement('tr');tr.dataset.taskId=t.id;tr.classList.toggle('selected',t.id===selected);tr.setAttribute('aria-selected',String(t.id===selected));
  tr.classList.toggle('active-row',isActive);
  const cells=Array.from({length:6},()=>{const td=document.createElement('td');tr.append(td);return td;});
  if(editing===t.id){
   const form=document.createElement('form');form.className='rename';const field=document.createElement('input');field.value=editName;field.maxLength=100;field.ariaLabel='New name for '+t.name;field.dataset.editId=t.id;field.oninput=()=>editName=field.value;
   const save=button('Save','Save name for '+t.name,()=>send('rename',{id:t.id,name:editName}),!online());
   form.onsubmit=e=>{e.preventDefault();send('rename',{id:t.id,name:editName});};form.append(field,save,button('Cancel','Cancel rename',()=>{editing='';renderTable();}));cells[0].append(form);
  }else{
   const name=button(t.name,'Select '+t.name,()=>select(t.id));name.className='row-name';
   if(counts.get(t.name)>1){const s=document.createElement('small');s.textContent=date(t.updated_at)+(t.updated_at?' · ':'')+'Copy '+(index+1);name.append(s);}cells[0].append(name);
  }
  cells[1].textContent=duration(t.duration_ms);cells[2].textContent=t.steps??'—';cells[3].textContent=date(t.updated_at);
  cells[4].textContent=isActive?(mode==='running'?'Playing':mode==='pausing'?'Pausing…':mode==='recording_paused'?'Recording paused':mode==='paused'?'Paused':mode==='recording'?'Recording':'Starting…'):({completed:'Completed',stopped:'Stopped',interrupted:'Needs review',executing:'Interrupted',running:'Interrupted',paused:'Interrupted'}[t.result]||t.result||'Saved');
  if(!isActive&&t.attention?.length){cells[4].replaceChildren(button('Needs attention','Review step '+t.attention[0].step+' of '+t.name,()=>review(t.id)));cells[4].firstChild.className='needs-attention';}
  const actions=document.createElement('div');actions.className='actions';
  actions.append(button('▶ Play','Play '+t.name,()=>play(t.id),!online()||!modern()||active()||starting()));
  if(isActive){
   if(mode==='running')actions.append(button('Pause','Pause '+t.name,()=>send('pause')));
   if(mode==='paused'&&state.can_resume||mode==='recording_paused')actions.append(button('Resume','Resume '+t.name,()=>send('resume')));
   actions.append(button('Stop','Stop '+t.name,stop,!online()));
  }
  actions.append(button('Rename','Rename '+t.name,()=>{editing=t.id;editName=t.name;confirmDelete='';renderTable();},isActive||!online()||!modern()));
  const trash=button('','Delete '+t.name,()=>{confirmDelete=t.id;editing='';renderTable();},!online()||!modern());trash.className='icon';
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('width','14');svg.setAttribute('height','14');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.8');svg.setAttribute('aria-hidden','true');
  const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d','M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7');svg.append(path);trash.append(svg);actions.append(trash);cells[5].append(actions);
  if(confirmDelete===t.id){const c=document.createElement('div');c.className='confirm';c.append(document.createTextNode('Delete '+t.name+'? '),button('Delete','Confirm delete '+t.name,()=>send('delete',{id:t.id}),!online()||[...pending.values()].some(v=>v.kind==='delete'&&v.payload.id===t.id)),button('Cancel','Cancel delete '+t.name,()=>{confirmDelete='';renderTable();}));cells[5].append(c);}
  if(rowErrors.has(t.id)){const e=document.createElement('span');e.className='row-error';e.setAttribute('role','alert');e.textContent=rowErrors.get(t.id);cells[5].append(e);}
  if(cached?.node.parentNode===table)cached.node.replaceWith(tr);else table.insertBefore(tr,table.children[index]||null);
  if(table.children[index]!==tr)table.insertBefore(tr,table.children[index]||null);
  rowCache.set(t.id,{signature:rowSignature,node:tr});
 });
 for(const [id,cached] of rowCache)if(!seen.has(id)){cached.node.remove();rowCache.delete(id);}
 if(focusId){const field=[...$('recordings').querySelectorAll('input')].find(e=>e.dataset.editId===focusId);if(field){field.focus();field.setSelectionRange(start,end);}}
}
function render(){
 if(!details||details.task.id!==selected)$('inputs').replaceChildren();
 $('pc').textContent=device?device.name+' · '+(online()?'Connected':'Offline'):'No PC connected';
 $('setup').hidden=online();$('setupText').textContent=device?'Start Task Recorder from the Windows Start menu on '+device.name+'.':'Connect your Windows PC once to get started.';
 $('seen').textContent=device?'Last seen '+date(device.last_seen*1000):'';
 $('selectedSettings').hidden=!selected;$('selectedName').textContent=tasks().find(t=>t.id===selected)?.name||'';
 $('reusable').disabled=!online()||!modern()||active()||starting();
 renderControls();renderTable();renderAttention();fit();
}
function review(id){select(id);renderAttention();$('attention').scrollIntoView({block:'nearest'});}
function renderAttention(){
 const task=tasks().find(t=>t.id===selected),issue=task?.attention?.[0];
 $('attention').hidden=!issue;if(!issue)return;
 $('attentionHeading').textContent='Needs attention · Step '+issue.step+(issue.kind==='interrupted'?' · Interrupted recording':'');
 $('attentionReason').textContent=issue.explanation||issue.reason;
 $('recordedReason').textContent=issue.explanation!==issue.reason?'Recorded reason: '+issue.reason:'';
 const key=task.id+task.revision;if(key!==attentionKey){attentionKey=key;$('correctionValue').value='';}
 $('repairCopy').disabled=!online()||state.protocol<3||active()||[...pending.values()].some(c=>c.kind==='repair-copy');
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
$('recordReplacement').onclick=()=>{
 const task=tasks().find(t=>t.id===selected);$('name').value=(task?.name||'Recording')+' — replacement';
 notice('Press Record, perform the intended actions in the marked browser, then Stop. The original is preserved.');$('name').focus();
};
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
   transportOK=false;error('Connection unavailable. Check your internet connection and refresh.');render();
   await pollDelay(Math.min(30000,(1600+800*Math.random())*2**Math.min(failures++,4)));
  }finally{pollAbort=null;}
 }}finally{pollRunning=false;}
}
$('record').onclick=()=>send('record',{name:$('name').value.trim(),...($('website').value?{url:$('website').value}:{})});
$('play').onclick=()=>play(selected);$('pause').onclick=()=>send('pause');$('resume').onclick=()=>send('resume');$('stop').onclick=stop;$('view').onclick=()=>send('view');
$('reusable').onclick=async()=>{if(!selected)return;const id=selected;if(await send('reusable',{id}))await inspect(id);};
$('startup').onchange=()=>send('startup',{enabled:$('startup').checked});
$('revoke').onclick=async()=>{if(!device)return;try{await api('revoke',{device_id:device.id});device=null;state={};after='';lastSeq=-1;error('');render();}catch(e){error(e.message);}};
$('pair').onclick=async()=>{try{const data=await api('pairing',{});$('challenge').hidden=false;$('code').textContent=data.code;$('approve').href='http://127.0.0.1:18931/pair#'+new URLSearchParams({origin:location.origin,code:data.code}).toString();error('');fit();}catch(e){error(e.message);}};
$('refresh').onclick=()=>{after='';pollAbort?.abort();document.dispatchEvent(new Event('visibilitychange'));};
// Fit the same-origin OS frame to content: the OS owns vertical scrolling.
// Scroll events move only the compact toolbar inside the frame; no polling or
// desktop capture. Direct diagnostic viewing uses ordinary CSS sticky positioning.
let frame=null,fitQueued=false;
try{if(window.parent!==window&&window.parent.location.origin===location.origin)frame=window.frameElement;}catch{}
function sticky(){if(!frame)return;const top=frame.getBoundingClientRect().top;const y=Math.min(Math.max(0,64-top-$('toolbar').offsetTop),Math.max(0,document.querySelector('main').offsetHeight-$('toolbar').offsetTop-$('toolbar').offsetHeight));$('toolbar').style.transform=`translateY(${y}px)`;}
function fit(){if(!frame||fitQueued)return;fitQueued=true;requestAnimationFrame(()=>{fitQueued=false;frame.style.height=Math.ceil(document.querySelector('main').offsetHeight+2)+'px';sticky();});}
if(frame){new ResizeObserver(fit).observe(document.querySelector('main'));window.parent.addEventListener('scroll',sticky,true);window.parent.addEventListener('resize',fit);}
document.addEventListener('visibilitychange',()=>{if(document.hidden)pollAbort?.abort();});
window.addEventListener('pageshow',()=>{stopped=false;after='';if(frame){window.parent.addEventListener('scroll',sticky,true);window.parent.addEventListener('resize',fit);}poll();});
window.addEventListener('pagehide',()=>{stopped=true;for(const request of requests)request.abort();if(frame){window.parent.removeEventListener('scroll',sticky,true);window.parent.removeEventListener('resize',fit);}});
poll();
