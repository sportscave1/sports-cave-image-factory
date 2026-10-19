'use strict';
const $ = id => document.getElementById(id);
const actions = ['navigate','wait_url','click','fill','select','check','upload','wait','unsupported'];
const bys = ['role','label','test_id','id','placeholder','text'];
const roles = ['button','link','textbox','checkbox','radio','combobox','option','heading','tab','menuitem'];
let key = new URLSearchParams(location.hash.slice(1)).get('key') || sessionStorage.getItem('recorder-key') || '';
history.replaceState(null,'',location.pathname);
if (key) sessionStorage.setItem('recorder-key',key);
let draft = {version:1,name:'Untitled task',inputs:[],steps:[]}, values = {}, state = {}, pending = false, dirty = false;
$('url').value = location.origin + '/demo';
function el(tag,text,cls) { const e=document.createElement(tag); if(text!==undefined)e.textContent=text; if(cls)e.className=cls; return e; }
function button(text,click,title) {const e=el('button',text);e.onclick=click;if(title)e.title=title;return e;}
function input(value,change,label) {const e=el('input');e.value=value??'';e.oninput=()=>{change(e.value);dirty=true;};if(label)e.setAttribute('aria-label',label);return e;}
function select(options,value,change,label) {const e=el('select');options.forEach(v=>{const o=el('option',v);o.value=v;e.append(o);});e.value=value;e.onchange=()=>{change(e.value);dirty=true;};if(label)e.setAttribute('aria-label',label);return e;}
function showError(message) {$('error').textContent=message||'';$('error').hidden=!message;}
async function api(name,data={}) {
  const r=await fetch('/api/'+name,{method:'POST',headers:{'Content-Type':'application/json','X-Recorder-Key':key},body:JSON.stringify(data)});
  const body=await r.json();
  if(!r.ok){if(r.status===401){$('pair').hidden=false;$('connection').textContent='Disconnected';}throw Error(body.error||'Local connection failed.');}
  $('connection').textContent='● Local runner connected';$('pair').hidden=true;return body;
}
function accept(s,replace=false) {
  state=s;
  if(replace || s.recording || s.mode==='recording_paused') {draft=structuredClone(s.draft);renderEditor();}
  $('progress').textContent=(s.total?'Step '+s.step+'/'+s.total+' · '+s.action+' · ':'')+s.message;
  const active=['running','paused','recording','recording_paused'].includes(s.mode);
  for(const id of ['new','save','play','addStep','addInput','open']) $(id).disabled=active;
  $('record').disabled=active||!s.browser_open;
  $('recordStop').disabled=!['recording','recording_paused'].includes(s.mode);
  $('pause').disabled=!['recording','running'].includes(s.mode);
  $('resume').disabled=!(s.mode==='recording_paused'||(s.mode==='paused'&&s.can_resume));
  $('name').disabled=active;
  document.querySelectorAll('#steps input,#steps select,#steps button,#inputs input,#inputs button').forEach(e=>e.disabled=active);
  document.querySelectorAll('#steps tr').forEach((e,i)=>e.classList.toggle('current',!!s.total&&i===s.step-1));
  renderTasks(s.tasks);
}
async function command(name,data={},replace=false) {
  if(pending)return;
  pending=true;showError('');
  try{accept(await api(name,data),replace);}catch(e){showError(e.message);}finally{pending=false;}
}
function renderTasks(tasks=[]) {
  $('tasks').replaceChildren();
  if(!tasks.length)$('tasks').append(el('p','No saved tasks yet.','hint'));
  for(const t of tasks) {
    const b=button(t.name,async()=>{
      if(dirty&&!confirm('Discard unsaved task edits?'))return;
      values={};dirty=false;await command('load',{id:t.id},true);
    });
    b.className='saved';
    const date=t.last_run?new Date(t.last_run).toLocaleString():'Never run';
    b.append(el('small',date+' · '+t.result));
    b.disabled=['running','paused','recording','recording_paused'].includes(state.mode);
    $('tasks').append(b);
  }
}
function valueText(value) {return value&&typeof value==='object'?'{{'+value.input+'}}':String(value??'');}
function parseValue(value,action) {
  const match=/^\{\{([a-z][a-z0-9_]*)\}\}$/.exec(value.trim());
  if(match)return {input:match[1]};
  return action==='check'?value==='true':value;
}
function defaultStep(action) {
  const s={action};
  if(!['navigate','wait_url','unsupported'].includes(action))s.locator={by:'role',role:'button',value:''};
  if(['navigate','wait_url','fill','select','check','upload'].includes(action))s.value=action==='check'?true:'';
  if(action==='unsupported')s.reason='Replace with a supported action or remove after review.';
  return s;
}
function renderEditor() {
  $('name').value=draft.name;
  $('steps').replaceChildren();$('stepCount').textContent='('+draft.steps.length+')';
  draft.steps.forEach((s,i)=>{
    const row=el('tr',undefined,s.action==='unsupported'?'unsupported':'');
    const action=el('td');action.append(el('small',String(i+1)));
    action.append(select(actions,s.action,v=>{draft.steps[i]=defaultStep(v);renderEditor();},'Action '+(i+1)));
    const timeout=input(s.timeout_ms||8000,v=>s.timeout_ms=Number(v),'Timeout milliseconds '+(i+1));timeout.type='number';timeout.min='500';timeout.max='30000';timeout.title='Wait timeout (ms)';action.append(timeout);
    const target=el('td');
    if(s.locator) {
      target.append(select(bys,s.locator.by,v=>{s.locator.by=v;if(v==='role')s.locator.role='button';else delete s.locator.role;renderEditor();},'Locator type '+(i+1)));
      if(s.locator.by==='role')target.append(select(roles,s.locator.role,v=>s.locator.role=v,'Role '+(i+1)));
      target.append(input(s.locator.value,v=>s.locator.value=v,'Locator value '+(i+1)));
    } else target.append(el('span',['navigate','wait_url'].includes(s.action)?'HTTP(S) address':'Needs review'));
    const value=el('td');
    if('value' in s)value.append(input(valueText(s.value),v=>s.value=parseValue(v,s.action),'Step value '+(i+1)));
    if(s.action==='unsupported')value.append(el('span',s.reason));
    const ops=el('td');
    ops.append(button('↑',()=>{if(i){[draft.steps[i-1],draft.steps[i]]=[s,draft.steps[i-1]];dirty=true;renderEditor();}},'Move up'));
    ops.append(button('↓',()=>{if(i<draft.steps.length-1){[draft.steps[i+1],draft.steps[i]]=[s,draft.steps[i+1]];dirty=true;renderEditor();}},'Move down'));
    ops.append(button('×',()=>{draft.steps.splice(i,1);dirty=true;renderEditor();},'Remove step'));
    row.append(action,target,value,ops);$('steps').append(row);
  });
  $('inputs').replaceChildren();
  draft.inputs.forEach((item,i)=>{
    const row=el('div',undefined,'inputRow');
    row.append(input(item.name,v=>{const old=item.name;item.name=v;values[v]=values[old]||'';delete values[old];for(const s of draft.steps)if(s.value?.input===old)s.value.input=v;},'Input name '+(i+1)));
    row.append(input(values[item.name]||'',v=>values[item.name]=v,'Input value '+(i+1)));
    const label=el('label','Required ');
    const check=el('input');check.type='checkbox';check.checked=item.required;check.onchange=()=>{item.required=check.checked;dirty=true;};label.append(check);row.append(label);
    row.append(button('×',()=>{draft.inputs.splice(i,1);dirty=true;renderEditor();},'Remove input'));
    $('inputs').append(row);
  });
}
$('name').oninput=()=>{draft.name=$('name').value;dirty=true;};
$('new').onclick=()=>{if(dirty&&!confirm('Discard unsaved edits?'))return;values={};dirty=false;command('new',{},true);};
$('open').onclick=()=>command('open',{url:$('url').value});
$('demo').onclick=()=>{$('url').value=location.origin+'/demo';};
$('record').onclick=()=>command('record',{task:draft},true);
$('recordStop').onclick=()=>command('record-stop',{},true);
$('save').onclick=async()=>{await command('save',{task:draft},true);if(!$('error').textContent)dirty=false;};
$('play').onclick=async()=>{
  if(pending)return;
  pending=true;showError('');
  try{
    const previous=state.tasks?.find(t=>t.id===draft.id);
    if(previous&&['interrupted','stopped','executing','paused','running'].includes(previous.result)&&
       !confirm('This task was interrupted. Inspect previous submissions first. Start a NEW run from step 1?'))return;
    const saved=await api('save',{task:draft});draft=structuredClone(saved.draft);dirty=false;
    accept(await api('play',{id:draft.id,values}),true);
  }catch(e){showError(e.message);}finally{pending=false;}
};
$('pause').onclick=()=>command('pause');
$('resume').onclick=()=>command('resume');
$('stop').onclick=()=>command('stop');
$('addStep').onclick=()=>{draft.steps.push(defaultStep('click'));dirty=true;renderEditor();};
$('addInput').onclick=()=>{let n=1;while(draft.inputs.some(i=>i.name==='input_'+n))n++;draft.inputs.push({name:'input_'+n,required:true});dirty=true;renderEditor();};
$('preview').onclick=async()=>{
  try {
    const p=await api('preview'),canvas=$('canvas'),ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);
    $('previewNote').textContent=p.blocked?'Preview blocked during sign-in or sensitive content.':'Refreshed '+new Date().toLocaleTimeString()+'. Layout only; page text, images and values removed.';
    if(p.blocked)return;
    const scale=Math.min(canvas.width/p.width,canvas.height/p.height);
    for(const r of p.boxes){ctx.fillStyle=r.kind==='field'?'#415c70':r.kind==='button'?'#a18c53':'#263646';ctx.fillRect(r.x*scale,r.y*scale,r.w*scale,Math.max(2,r.h*scale));}
  }catch(e){showError(e.message);}
};
$('connect').onclick=()=>{key=$('key').value;$('key').value='';sessionStorage.setItem('recorder-key',key);poll(true);};
$('copyKey').onclick=async()=>{try{await navigator.clipboard.writeText(key);$('progress').textContent='Connection key copied for the local embedded page. Treat it as a password; it expires when the runner restarts.';}catch{showError('Clipboard permission unavailable. Use the launcher console directly.');}};
$('refresh').onclick=()=>poll(false);
async function poll(replace=false) {
  if(pending)return;
  try{accept(await api('state'),replace);}catch(e){$('connection').textContent='Disconnected';if(!key)$('pair').hidden=false;else showError(e.message);}
}
async function tick(){if(!document.hidden)await poll();setTimeout(tick,2000);}
renderEditor();poll(true);setTimeout(tick,2000);
