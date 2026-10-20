'use strict';
const $=id=>document.getElementById(id),base='/api/task-recorder/';
let devices=[],device=null,state={},selected='',runnerSelected='',after='',stopped=false,pending=false,values={},detail=null,reconciled=false;
const uuid=()=>crypto.randomUUID();
function message(error){$('error').textContent=error||'';$('error').hidden=!error;}
async function api(path,data,signal){
 const response=await fetch(base+path,{method:data===undefined?'GET':'POST',credentials:'same-origin',headers:data===undefined?{}:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data),signal});
 const result=await response.json();if(!response.ok)throw Error(result.error||'Connection unavailable. Try again.');return result;
}
async function send(kind,payload={},reuse){
 if(!device)return message('Start Task Recorder on your PC, or choose Connect PC.');
 if(['record','play'].includes(kind)&&pending&&!reuse)return;
 const command={device_id:device.id,id:reuse||uuid(),kind,payload};
 pending=['record','play'].includes(kind);renderControls();
 if(pending)sessionStorage.setItem('recorder-pending',JSON.stringify(command));
 try{
   let result=await api('command',command);
   for(let n=0;n<100&&['queued','dispatched'].includes(result.status);n++){
     await new Promise(resolve=>setTimeout(resolve,250));
     result=await api('receipt?device='+encodeURIComponent(device.id)+'&id='+command.id);
   }
   if(result.status!=='applied')throw Error(result.receipt?.message||'This control was not confirmed. Check the browser, then press Stop.');
   if(kind==='inspect'){detail=result.receipt;renderDetail();}
   if(kind==='reusable'){await send('inspect');}
   message('');
   if(sessionStorage.getItem('recorder-pending')&&JSON.parse(sessionStorage.getItem('recorder-pending')).id===command.id)sessionStorage.removeItem('recorder-pending');
 }catch(error){message(error.message);}
 finally{pending=false;renderControls();after='';}
}
function renderControls(){
 const online=!!device?.connected,mode=state.mode||'idle';
 const recording=mode==='recording'||mode==='recording_paused',playing=['running','paused','starting'].includes(mode)||pending;
 $('record').hidden=recording||playing||!!device?.needs_review;
 $('play').hidden=recording||playing||!selected||!!device?.needs_review;
 $('stop').hidden=!(recording||playing||device?.needs_review||mode==='interrupted');
 $('resume').hidden=!(mode==='recording_paused'||(mode==='paused'&&state.can_resume));
 for(const name of ['record','play','stop','resume','view'])$(name).disabled=!online;
 $('saved').disabled=recording||playing;
 $('message').textContent=device?.needs_review?'Previous run interrupted. Check the browser, then press Stop.':state.message||'Ready';
 if(mode==='running')$('message').textContent='Playing · '+state.step+' of '+state.total;
}
function render(){
 device=devices.find(d=>d.id===device?.id)||devices[0]||null;state=device?.state||{};
 $('pc').textContent=device?device.name+' · '+(device.connected?'Connected':'Offline'):'No PC connected';
 $('setup').hidden=!!device?.connected;$('setupText').textContent=device?'Start Task Recorder from the Start menu on '+device.name+'.':'Connect your Windows PC once to get started.';
 const tasks=state.tasks||[],next=state.selected_id;
 if(next&&tasks.some(t=>t.id===next)&&next!==runnerSelected){selected=next;runnerSelected=next;values={};detail=null;}
 if(selected&&!tasks.some(t=>t.id===selected))selected='';
 const signature=JSON.stringify(tasks.map(t=>[t.id,t.name,t.revision]));
 if($('saved').dataset.signature!==signature){
   $('saved').replaceChildren();const empty=document.createElement('option');empty.value='';empty.textContent=tasks.length?'Choose a recording':'No recordings yet';$('saved').append(empty);
   for(const task of tasks){const option=document.createElement('option');option.value=task.id;option.textContent=task.name;$('saved').append(option);}
   $('saved').dataset.signature=signature;
 }
 $('saved').value=selected;$('savedLabel').hidden=$('saved').hidden=tasks.length===0;
 $('seen').textContent=device?'Last seen '+new Date(device.last_seen*1000).toLocaleTimeString():'';
 $('startup').checked=!!state.startup;renderControls();
}
async function poll(){
 while(!stopped){
  try{
   const result=await api('state'+(device?'?device='+encodeURIComponent(device.id)+(after?'&after='+after:''):''));
   devices=result.devices;render();after=device?String(device.seq):'';
   if(device&&!reconciled){reconciled=true;reconcile();}
   if(!device)await new Promise(r=>setTimeout(r,5000));
  }catch(error){$('pc').textContent='Connection unavailable';message(error.message);await new Promise(r=>setTimeout(r,3000));}
 }
}
async function reconcile(){
 const saved=sessionStorage.getItem('recorder-pending');if(!saved)return;
 try{
  const previous=JSON.parse(saved);if(previous.device_id!==device.id)return;
  pending=true;renderControls();
  const result=await api('receipt?device='+encodeURIComponent(device.id)+'&id='+previous.id);
  if(['queued','dispatched'].includes(result.status))await send(previous.kind,previous.payload,previous.id);
  else {sessionStorage.removeItem('recorder-pending');if(result.status!=='applied')message(result.receipt?.message||'The previous start was interrupted. Press Stop before trying again.');}
 }catch{message('The previous start could not be confirmed. Press Stop before trying again.');}
 finally{pending=false;renderControls();}
}
function renderDetail(){
 $('detail').hidden=false;$('taskJson').value=JSON.stringify(detail.task,null,2);$('rename').value=detail.task.name;
 values={...detail.values};$('inputs').replaceChildren();
 for(const input of detail.task.inputs){
   const label=document.createElement('label');label.textContent=input.name.replaceAll('_',' ');
   const field=document.createElement('input');field.value=values[input.name]||'';field.setAttribute('aria-label',label.textContent);field.oninput=()=>values[input.name]=field.value;
   $('inputs').append(label,field);
 }
}
$('record').onclick=()=>send('record',$('website').value?{url:$('website').value}:{});
$('stop').onclick=()=>send(state.recording||state.mode==='recording_paused'?'stop-save':'stop');
$('play').onclick=()=>{const task=state.tasks?.find(t=>t.id===selected);if(task)send('play',{id:task.id,revision:task.revision,values});};
$('resume').onclick=()=>send('resume');$('pause').onclick=()=>send('pause');$('view').onclick=()=>send('view');
$('new').onclick=()=>{selected='';detail=null;values={};send('new');};
$('saved').onchange=()=>{selected=$('saved').value;detail=null;values={};$('detail').hidden=true;if(selected)send('load',{id:selected});};
$('renameButton').onclick=()=>send('rename',{name:$('rename').value});
$('inspect').onclick=()=>send('inspect');$('reusable').onclick=()=>send('reusable');
$('edit').onclick=()=>{try{send('edit',{task:JSON.parse($('taskJson').value)});}catch{message('Check the step format before saving.');}};
$('files').onclick=()=>send('choose-files');$('startup').onchange=()=>send('startup',{enabled:$('startup').checked});
$('revoke').onclick=async()=>{if(!device)return;if(!confirm('Disconnect this PC? You will need to approve pairing on the PC again.'))return;try{await api('revoke',{device_id:device.id});device=null;after='';}catch(e){message(e.message);}};
$('pair').onclick=async()=>{try{const data=await api('pairing',{});$('challenge').hidden=false;$('code').textContent=data.code;$('approve').href='http://127.0.0.1:18931/pair#'+new URLSearchParams({origin:location.origin,code:data.code}).toString();message('');}catch(e){message(e.message);}};
$('refresh').onclick=()=>{after='';api('state').then(r=>{devices=r.devices;render();}).catch(e=>message(e.message));};
window.addEventListener('pagehide',()=>{stopped=true;});
poll();
