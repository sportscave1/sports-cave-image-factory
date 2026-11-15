// Loaded only when Edit opens. No timers, screenshots or separate execution path.
export function createEditor(host, options) {
 const {task, revision, send, canEdit, changed, close} = options;
 const clone=value=>JSON.parse(JSON.stringify(value));
 let steps=task.steps.map((step,index)=>({ref:{source:index},step:clone(step)})),undo=[],chosen=new Set(),errors={},saving=false,capture=null,review=null;
 const make=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
 const action=(label,fn)=>{const b=make('button',label);b.type='button';b.onclick=fn;return b;};
 const field=(label,value,type='text')=>{const l=make('label',label),f=make('input');f.type=type;if(type==='checkbox')f.checked=value===true||value==='true';else f.value=value??'';l.append(f);return [l,f];};
 const back=action('Back / Cancel',()=>{if(!capture&&!saving)close();}),save=action('Save edited copy',saveCopy);
 const heading=make('h2','Edit '+task.name),nameLabel=field('Edited copy name',task.name.slice(0,91)+' — edited'),name=nameLabel[1];name.maxLength=100;
 const intro=make('p','The original stays unchanged. Review the numbered sequence before saving. The copy has no recorded duration and starts as not yet run.');
 const tools=make('div');tools.className='editor-tools';
 const undoButton=action('Undo',()=>{const previous=undo.pop();if(previous){steps=previous;chosen.clear();errors={};draw();}});
 const remove=action('Delete selected',()=>mutate(()=>steps=steps.filter((_,i)=>!chosen.has(i))));
 const rangeStart=field('Keep from step',1,'number'),rangeEnd=field('through step',steps.length,'number');
 const trim=action('Keep this range',()=>{const start=Number(rangeStart[1].value),end=Number(rangeEnd[1].value);if(!Number.isInteger(start)||!Number.isInteger(end)||start<1||end<start||end>steps.length){message.textContent='Choose a valid first and last step to keep.';return;}mutate(()=>steps=steps.slice(start-1,end));});
 tools.append(undoButton,remove,rangeStart[0],rangeEnd[0],trim);
 const add=make('div');add.className='editor-tools';const kind=make('select');kind.ariaLabel='Readiness check';
 for(const [value,label] of [['wait','Wait for visible text'],['wait_url','Wait for website address']]){const o=make('option',label);o.value=value;kind.append(o);}
 const check=field('Text or website address',''),position=field('Insert after step',steps.length,'number');position[1].min=0;
 add.append(kind,check[0],position[0],action('Add readiness check',()=>{const value=check[1].value.trim(),at=Number(position[1].value);if(!value||!Number.isInteger(at)||at<0||at>steps.length){message.textContent='Enter the expected text or address and choose a position (0 means the beginning).';return;}const entry={ref:{check:{action:kind.value,value}},step:kind.value==='wait'?{action:'wait',locator:{by:'text',value},timeout_ms:30000}:{action:'wait_url',value,timeout_ms:30000}};mutate(()=>steps.splice(at,0,entry));check[1].value='';}));
 const message=make('p');message.setAttribute('role','alert');message.className='editor-error';
 const captureBox=make('div');captureBox.className='editor-capture';captureBox.hidden=true;
 const list=make('ol');list.className='editor-steps';
 const header=make('div');header.className='editor-tools';header.append(back,heading,save);
 host.replaceChildren(header,nameLabel[0],intro,tools,add,message,captureBox,list);host.hidden=false;
 function checkpoint(){undo.push(clone(steps));if(undo.length>30)undo.shift();}
 function mutate(fn){if(!canEdit()||saving||capture)return;checkpoint();fn();chosen.clear();errors={};message.textContent='';draw();}
 function target(step){const loc=step.locator;if(!loc)return '';if(['id','test_id'].includes(loc.by))return 'the recorded '+(step.action==='click'?'control':'field');return '“'+loc.value+'”';}
 function label(step){return ({navigate:'Open website',wait_url:'Wait for website address',click:'Click',fill:'Enter text in',select:'Choose in',check:'Set checkbox',upload:'Choose file for',wait:'Wait for visible',unsupported:'Needs attention'}[step.action]||'Needs attention')+(target(step)?' '+target(step):'');}
 function displayValue(step){const value=step.value;if(value&&typeof value==='object'){if(value.file)return 'Saved file on your PC';return options.values?.[value.input]??'';}return value??'';}
 function editValue(entry,input){let checkpointed=false;input.oninput=()=>{if(!checkpointed){checkpoint();checkpointed=true;}entry.step.value=input.type==='checkbox'?input.checked:input.value;entry.ref.value=clone(entry.step.value);delete errors[String(steps.indexOf(entry))];input.closest('li')?.querySelector('.editor-error')?.remove();refresh();};}
 function draw(){
  list.replaceChildren();
  steps.forEach((entry,index)=>{
   const step=entry.step,li=make('li');li.dataset.step=String(index+1);
   const line=make('div');line.className='editor-step-line';const selection=field('Select step '+(index+1),chosen.has(index),'checkbox');selection[0].className='step-select';selection[1].onchange=()=>{selection[1].checked?chosen.add(index):chosen.delete(index);refresh();};
   const title=make('strong',label(step));line.append(selection[0],title);
   if(step.action==='unsupported'){const warning=make('span',step.reason);warning.className='editor-warning';li.append(warning);}
   else if(entry.ref.check){
    const [l,input]=field('Value for step '+(index+1),entry.ref.check.value);l.className='step-value';let checkpointed=false;
    input.oninput=()=>{if(!checkpointed){checkpoint();checkpointed=true;}entry.ref.check.value=input.value;if(step.action==='wait')step.locator.value=input.value;else step.value=input.value;refresh();};line.append(l);
   }else if(step.action==='upload'){
    const value=make('span',displayValue(step)),choose=action('Choose file on PC',async()=>{const result=await send('edit-file',{id:task.id,revision});if(result){mutate(()=>{entry.ref.value=result.value;entry.step.value=result.value;});}});line.append(value,choose);
   }else if(['fill','select','navigate','wait_url','check'].includes(step.action)&&!entry.ref.check){
    const [l,input]=field('Value for step '+(index+1),displayValue(step),step.action==='check'?'checkbox':'text');l.className='step-value';editValue(entry,input);line.append(l);
   }else if(step.action==='wait_url')line.append(make('span',step.value));
   if(step.action==='wait'||step.action==='wait_url')li.append(make('small','Readiness check · up to '+((step.timeout_ms??8000)/1000)+' seconds'));
   line.append(action('Replace by recording',()=>beginReplacement(index)),action('Delete step',()=>mutate(()=>steps.splice(index,1))));
   li.prepend(line);if(errors[String(index)]){const e=make('p',errors[String(index)]);e.className='editor-error';e.setAttribute('role','alert');li.append(e);}list.append(li);
  });
  rangeStart[1].max=rangeEnd[1].max=steps.length;rangeEnd[1].value=steps.length;position[1].max=steps.length;position[1].value=steps.length;
  refresh();changed();
 }
 async function beginReplacement(index){
  if(!canEdit()||capture||saving)return;
  message.textContent='Perform only the replacement actions in the marked recorder browser, then Stop replacement. You will review them before insertion.';
  const context=[...steps.slice(0,index+1)].reverse().find(entry=>entry.ref.source!==undefined)?.ref.source??0;
  const result=await send('record-replacement',{id:task.id,revision,step:context});
  if(!result)return;
  capture={id:result.replacement_id,index};showCapture();refresh();
 }
 function showCapture(){
  captureBox.hidden=false;captureBox.replaceChildren(make('strong','Recording replacement'));
  captureBox.append(make('p','Use the dedicated recorder browser. Stop to save and review the replacement.'));
  captureBox.append(action('View browser',()=>send('view')),action('Stop replacement',finishReplacement));changed();
 }
 async function finishReplacement(){
  if(!capture)return;const current=capture;
  if(options.isRecording()){if(!await send('stop-save'))return;}
  const result=await send('inspect',{id:current.id});if(!result)return;
  review={task:result.task,index:current.index,taskRevision:result.revision};capture=null;
  const refs=review.task.steps.map((_,i)=>i);captureBox.replaceChildren(make('strong','Review replacement actions'));
  captureBox.append(make('p','Keep only the replacement actions you intended. A separate replacement recording is retained in the table.'));
  const reviewList=make('ol');review.task.steps.forEach((step,i)=>{const li=make('li'),[l,f]=field(label(step)+(step.reason?' · '+step.reason:'')+(typeof step.value==='string'?' · '+step.value:''),true,'checkbox');f.onchange=()=>{if(f.checked)refs.push(i);else refs.splice(refs.indexOf(i),1);};li.append(l);reviewList.append(li);});captureBox.append(reviewList);
  captureBox.append(action('Use reviewed replacement',()=>{if(!canEdit())return;if(!refs.length){message.textContent='Keep at least one replacement action.';return;}const fragment=review.task,items=[...new Set(refs)].sort((a,b)=>a-b).map(i=>({ref:{recording:{id:fragment.id,revision:review.taskRevision,step:i}},step:clone(fragment.steps[i])}));const at=review.index;review=null;mutate(()=>steps.splice(at,1,...items));captureBox.hidden=true;refresh();}),action('Discard replacement from edit',()=>{review=null;captureBox.hidden=true;refresh();}));
  refresh();changed();
 }
 async function saveCopy(){
  if(!canEdit()||saving||capture||review)return;
  if(!name.value.trim()||!steps.length){message.textContent='Enter a copy name and keep at least one action.';return;}
  saving=true;refresh();
  const result=await send('edit-copy',{id:task.id,revision,name:name.value.trim(),steps:steps.map(entry=>clone(entry.ref))});
  saving=false;if(result){close();return;}refresh();
 }
 function refresh(){
  const enabled=canEdit()&&!saving&&!capture&&!review;
  save.textContent=saving?'Saving…':'Save edited copy';
  save.disabled=!enabled||!steps.length;back.disabled=saving||!!capture;
  name.disabled=!enabled;undoButton.disabled=!enabled||!undo.length;remove.disabled=!enabled||!chosen.size;
  for(const node of [...tools.querySelectorAll('input,button'),...add.querySelectorAll('input,select,button'),...list.querySelectorAll('input,button')])node.disabled=!enabled;
  undoButton.disabled=!enabled||!undo.length;remove.disabled=!enabled||!chosen.size;
  if(capture&&!options.isRecording()){
   captureBox.firstChild.textContent='Replacement stopped';
  }
 }
 draw();
 return {refresh,showErrors(value){errors=value||{};message.textContent='Check the highlighted actions. Your edits are retained.';draw();},get capturing(){return !!capture;}};
}
