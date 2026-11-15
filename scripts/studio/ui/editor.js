let panel, request, showFrame, opened, dirty=false, busy=false, stack=[], selected="title", recoveryKey='';
let recoveryTimer,highlightFrame,lastSource='',undoBytes=0;
function scheduleRecovery(){if(!recoveryTimer)recoveryTimer=setTimeout(()=>{recoveryTimer=0;persist();},300);}
function scheduleHighlight(){if(!highlightFrame)highlightFrame=requestAnimationFrame(()=>{highlightFrame=0;if(panel)highlight();});}
const flushRecovery=()=>{clearTimeout(recoveryTimer);recoveryTimer=0;persist();};
const visibilityRecovery=()=>{if(document.visibilityState==='hidden')flushRecovery();};
function persist(){if(!recoveryKey||!opened)return;try{if(dirty)localStorage.setItem(recoveryKey,JSON.stringify({path:opened.path,hash:opened.hash,revision:opened.revision,selected,value:capture()}));else localStorage.removeItem(recoveryKey);}catch{msg('Browser recovery storage unavailable. Keep this editor open until changes are saved.');}}
function clearRecovery(){clearTimeout(recoveryTimer);recoveryTimer=0;try{if(recoveryKey)localStorage.removeItem(recoveryKey);}catch{}}
const $=id=>panel.querySelector("#"+id);
const beforeUnload=event=>{flushRecovery();if(dirty){event.preventDefault();event.returnValue="";}};
const esc=s=>s.replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");
const msg=s=>{$("ed-status").textContent=s;};
function confirmDiscard(message) {
  return new Promise(resolve=>{
    const dialog=document.createElement("dialog"), text=document.createElement("p"), yes=document.createElement("button"), no=document.createElement("button");
    text.textContent=message;yes.textContent="Discard changes";no.textContent="Keep editing";
    const finish=value=>{dialog.close();dialog.remove();resolve(value);};
    yes.onclick=()=>finish(true);no.onclick=()=>finish(false);
    dialog.oncancel=event=>{event.preventDefault();finish(false);};
    dialog.append(text,no,yes);document.body.append(dialog);dialog.showModal();no.focus();
  });
}
function highlight() {
  const field=$("ed-source"),lines=field.value.split("\n"),wrap=$("ed-wrap")?.checked;
  const columns=Math.max(12,Math.floor((field.clientWidth-24)/7.8)),firstRow=Math.max(0,Math.floor(field.scrollTop/20)-10),lastRow=firstRow+Math.ceil(field.clientHeight/20)+30;
  let row=0,start=0,end=lines.length,top=0,bottom=0;
  const heights=lines.map(line=>wrap?Math.max(1,Math.ceil(line.replaceAll('\t','  ').length/columns)):1);
  for(let i=0;i<lines.length;i++){if(row+heights[i]<firstRow){start=i+1;top=row+heights[i];}if(row>lastRow){end=i;break;}row+=heights[i];}
  bottom=heights.slice(end).reduce((a,b)=>a+b,0);
  const spacer=n=>'<span style="display:block;height:'+n*20+'px"></span>';
  $("ed-lines").innerHTML=spacer(top)+lines.slice(start,end).map((line,i)=>String(start+i+1)+(wrap?'\n'.repeat(heights[start+i]-1):'')).join('\n')+spacer(bottom);
  $("ed-highlight").innerHTML=spacer(top)+esc(lines.slice(start,end).join('\n')).replace(/(&lt;\/?[\w-]+|\b(?:const|let|function|return|if|else|var|class|import|export|async|await)\b|#[\da-fA-F]{3,8}\b)/g,'<span class="syntax">$1</span>')+'\n'+spacer(bottom);
  $("ed-highlight").scrollTop=field.scrollTop;$("ed-highlight").scrollLeft=field.scrollLeft;$("ed-lines").scrollTop=field.scrollTop;
}
function capture() {
  if(opened.path!=="app.py") return {source:$("ed-source").value};
  const changes={properties:{}};
  if($("ed-text")) changes.text=$("ed-text").value;
  panel.querySelectorAll("[data-property]").forEach(input=>{changes.properties[input.dataset.property]=input.value;});
  return changes;
}
function apply(value) {
  if(opened.path!=="app.py") { $("ed-source").value=value.source;lastSource=value.source;highlight(); }
  else {
    if($("ed-text")) $("ed-text").value=value.text;
    panel.querySelectorAll("[data-property]").forEach(input=>{input.value=value.properties[input.dataset.property]||"";});
  }
}
function modified() {
  dirty=true;
  if(opened.path!=='app.py'){
    const value=$("ed-source").value,old=lastSource;let start=0,end=0;
    while(start<old.length&&start<value.length&&old[start]===value[start])start++;
    while(end<old.length-start&&end<value.length-start&&old[old.length-1-end]===value[value.length-1-end])end++;
    const undo={start,removed:old.slice(start,old.length-end),inserted:value.length-start-end};
    undoBytes+=undo.removed.length*2;stack.push({undo});lastSource=value;
    // Inverse edits retain keystroke Undo without 100 complete file copies.
    while(stack.length>100||undoBytes>4*1024*1024&&stack.length>2){const dropped=stack.splice(1,1)[0];undoBytes-=(dropped.undo?.removed.length||0)*2;}
  }else{stack.push(capture());if(stack.length>100)stack.splice(1,1);}
  msg("Unsaved changes");scheduleRecovery();
}
function component() {
  const model=opened.visual[selected], area=$("ed-fields");
  area.replaceChildren();
  const field=(label,value,key)=>{
    const wrap=document.createElement("label"), input=document.createElement("input");
    wrap.textContent=label;wrap.dataset.fieldKind=key==="text"?"text":"style";input.value=value;
    if(key==="text")input.id="ed-text";else input.dataset.property=key;
    input.addEventListener("input",modified);wrap.append(input);area.append(wrap);
  };
  if("text" in model) field("Text",model.text,"text");
  for(const [key,value] of Object.entries(model.properties)) field(key,value,key);
  dirty=false;stack=[capture()];
}
function render() {
  $("ed-file").value=opened.path;
  $("ed-visual").hidden=opened.path!=="app.py";
  $("ed-code").hidden=opened.path==="app.py";
  $("ed-history").replaceChildren();
  for(const item of [...opened.history].reverse()) {
    const option=document.createElement("option");option.value=item.id;
    option.textContent=new Date(item.saved_at).toLocaleString()+" · "+item.operation;
    $("ed-history").append(option);
  }
  $("ed-restore").disabled=!opened.history.length;
  if(opened.visual) {
    $("ed-component").replaceChildren();
    for(const [key,model] of Object.entries(opened.visual)) {
      const option=document.createElement("option");option.value=key;option.textContent=model.label;
      $("ed-component").append(option);
    }
    $("ed-component").value=selected;component();
  } else { $("ed-source").value=opened.source;lastSource=opened.source;undoBytes=0;highlight();dirty=false;stack=[capture()]; }
  msg("Revision "+opened.revision+" · "+opened.path);
}
async function load(path) {
  opened=await request("/api/action",{action:"editor-open",path});render();
  if(recoveryKey){let saved;try{saved=JSON.parse(localStorage.getItem(recoveryKey)||'null');}catch{}if(saved?.path===path){if(opened.visual&&opened.visual[saved.selected]){selected=saved.selected;render();}const stale=saved.hash!==opened.hash||saved.revision!==opened.revision;apply(saved.value);opened.hash=saved.hash;opened.revision=saved.revision;dirty=true;stack.push(capture());msg(stale?'Recovered unsaved buffer; source changed. Save is blocked by the original hash/revision. Compare or explicitly discard.':'Recovered unsaved changes for this application draft.');}}
}
async function act(fn) {
  if(busy)return;busy=true;
  const disabled=new Map([...panel.querySelectorAll("button,input,select,textarea")].map(n=>[n,n.disabled]));
  disabled.forEach((_,n)=>n.disabled=true);
  try{await fn();}catch(error){msg(error.message);}
  finally{busy=false;disabled.forEach((value,n)=>n.disabled=value);$("ed-restore").disabled=!opened?.history.length;}
}
async function save(restore) {
  const data={action:"editor-save",path:opened.path,expected_hash:opened.hash,expected_revision:opened.revision};
  if(restore)data.restore=restore;
  else if(opened.path==="app.py") {
    data.component=selected;const current=capture(),base=opened.visual[selected];
    data.changes={properties:{}};
    if("text" in current && current.text!==base.text)data.changes.text=current.text;
    for(const [key,value]of Object.entries(current.properties))if(value!==base.properties[key])data.changes.properties[key]=value;
  } else data.source=$("ed-source").value;
  msg("Saving source and refreshing any running isolated preview…");
  const result=await request("/api/action",data);
  clearRecovery();dirty=false;
  await load(opened.path);
  panel.dispatchEvent(new CustomEvent("studio-saved",{bubbles:true,detail:{revision:opened.revision,path:opened.path}}));
  $("ed-diff").textContent=result.diff||"No source changes.";
  if(result.frame)await showFrame(result.frame);
  msg(result.preview_error||"Saved to the actual draft. Revision "+opened.revision+".");
}
export async function mount(target,transport,frameCallback,options={}) {
  panel=target;request=transport;showFrame=frameCallback;recoveryKey=options.recoveryKey?'studio-buffer:'+options.recoveryKey:'';
  if(!panel.dataset.mounted) {
    if(!document.querySelector("[data-studio-editor-css]")){const css=document.createElement("link");css.rel="stylesheet";css.href="/editor.css";css.dataset.studioEditorCss="true";document.head.append(css);}
    panel.innerHTML='<div class="heading"><div><p class="eyebrow">DRAFT EDITOR</p><h2>Make a focused change</h2></div><button id="ed-close">Close editor</button></div><p class="hint">Explicit component mappings only. The selected worktree is the source of truth. Live integrations remain disabled.</p><label>Editing target<select id="ed-file"></select></label><p id="ed-status" role="status"></p><div id="ed-visual"><label>Component<select id="ed-component"></select></label><p class="hint">Properties accept literal hex colours, CSS sizes, and supported alignment/layout values. Empty removes the override. Mobile panel settings apply below 760 px.</p><div id="ed-fields"></div></div><div id="ed-code" hidden><label>Search<input id="ed-search" placeholder="Find source text"></label><button id="ed-find">Find next</button><label><input id="ed-wrap" type="checkbox"> Word wrap</label><div class="code-wrap"><pre id="ed-lines" aria-hidden="true"></pre><div class="code-stack"><pre id="ed-highlight" aria-hidden="true"></pre><textarea id="ed-source" wrap="off" spellcheck="false" aria-label="Authorised source code"></textarea></div></div></div><div class="actions"><button class="primary" id="ed-save">Save Draft</button><button id="ed-undo">Undo</button><button id="ed-discard">Discard Unsaved Changes</button><button id="ed-changes">View Changes</button></div><label>Saved editor revision<select id="ed-history"></select></label><button id="ed-restore">Restore Revision</button><pre id="ed-diff" aria-label="Source changes"></pre>';
    $("ed-file").onchange=()=>act(async()=>{
      const path=$("ed-file").value;
      if(dirty&&!await confirmDiscard("Discard unsaved editor changes?")){$("ed-file").value=opened.path;return;}clearRecovery();
      await load(path);
    });
    $("ed-component").onchange=async()=>{
      if(dirty&&!await confirmDiscard("Discard unsaved component changes?")){$("ed-component").value=selected;return;}
      clearRecovery();selected=$("ed-component").value;component();msg("Editing "+opened.visual[selected].label);
    };
    $("ed-wrap").onchange=()=>{const on=$("ed-wrap").checked;$("ed-source").wrap=on?'soft':'off';$("ed-source").style.whiteSpace=on?'pre-wrap':'pre';$("ed-highlight").style.whiteSpace=on?'pre-wrap':'pre';$("ed-lines").hidden=false;highlight();};
    $("ed-source").onkeydown=e=>{if(e.key==='Tab'){e.preventDefault();const field=e.currentTarget,start=field.selectionStart,end=field.selectionEnd;field.setRangeText('  ',start,end,'end');modified();scheduleHighlight();}};
    $("ed-source").oninput=()=>{modified();scheduleHighlight();};
    $("ed-source").onscroll=scheduleHighlight;
    $("ed-find").onclick=()=>{
      const field=$("ed-source"),term=$("ed-search").value;
      let index=field.value.indexOf(term,field.selectionEnd);
      if(index<0)index=field.value.indexOf(term);
      if(index>=0&&term){field.focus();field.setSelectionRange(index,index+term.length);field.scrollTop=field.value.slice(0,index).split("\n").length*20-80;}
      else msg("No match.");
    };
    $("ed-save").onclick=()=>act(()=>save());
    $("ed-undo").onclick=()=>act(async()=>{
      if(dirty&&stack.length>1){const item=stack.pop();if(item.undo&&stack.length>1){const {start,removed,inserted}=item.undo,value=$("ed-source").value;undoBytes-=removed.length*2;apply({source:value.slice(0,start)+removed+value.slice(start+inserted)});}else{apply(stack.at(-1));undoBytes=0;}dirty=opened.path==='app.py'?stack.length>1:$("ed-source").value!==opened.source;msg(dirty?"Unsaved changes":"Local edits undone.");scheduleRecovery();return;}
      if(dirty){msg('Unsaved Undo history limit reached. Save or explicitly discard the retained buffer.');return;}
      const undone=new Set(opened.history.filter(h=>h.undo_of).map(h=>h.undo_of));
      const latest=[...opened.history].reverse().find(h=>h.operation!=="undo"&&!undone.has(h.id));
      if(latest)await save({id:latest.id,side:"before"});else msg("Nothing to undo.");
    });
    $("ed-discard").onclick=()=>act(async()=>{
      if(dirty&&!await confirmDiscard("Discard unsaved editor changes?"))return;
      clearRecovery();dirty=false;
      await load(opened.path);
    });
    $("ed-changes").onclick=()=>act(async()=>{
      const result=await request("/api/action",{action:"editor-diff",path:opened.path});
      $("ed-diff").textContent=result.diff||"No saved source changes.";
    });
    $("ed-restore").onclick=()=>act(async()=>{
      if(dirty&&!await confirmDiscard("Discard unsaved changes and restore the selected saved revision?"))return;
      await save({id:$("ed-history").value,side:"after"});
    });
    $("ed-close").onclick=async()=>{if(!dirty||await confirmDiscard("Discard unsaved changes and close?")){dirty=false;clearRecovery();panel.hidden=true;}};
    window.addEventListener("beforeunload",beforeUnload);
    window.addEventListener('pagehide',flushRecovery);document.addEventListener('visibilitychange',visibilityRecovery);
    panel.dataset.mounted="true";
  }
  panel.hidden=false;
  if(dirty)return;
  await act(async()=>{
    const listing=options.files?{files:options.files}:await request("/api/action",{action:"editor-files"});
    $("ed-file").replaceChildren();
    for(const file of listing.files){
      const option=document.createElement("option");option.value=file.path;
      option.textContent=(file.mode==="visual"?"Visual mappings · ":"")+file.path+(file.available?"":" · unavailable");
      option.disabled=!file.available;option.title=file.reason||"";$("ed-file").append(option);
    }
    let savedPath;try{savedPath=JSON.parse(localStorage.getItem(recoveryKey)||'null')?.path;}catch{}
    const path=listing.files.find(f=>f.available&&f.path===(savedPath||options.path||opened?.path))?.path||listing.files.find(f=>f.available)?.path;
    if(!path)throw Error("No authorised editor files are available in this draft.");
    await load(path);
  });
}

export async function canLeave(){if(busy)return false;if(!dirty)return true;if(!await confirmDiscard("Discard unsaved changes before changing draft or selection?"))return false;dirty=false;clearRecovery();return true;}
export async function selectFile(path){if(busy)return false;if(opened?.path===path&&dirty)return true;if(dirty&&!await canLeave())return false;let loaded=false;await act(async()=>{await load(path);loaded=true;});return loaded;}
export async function selectComponent(key){if(busy)return false;if(dirty&&!await canLeave())return false;let loaded=false;await act(async()=>{if(opened?.path!=="app.py")await load("app.py");if(!opened.visual[key])throw Error("Unmapped component");selected=key;render();loaded=true;});return loaded;}
export async function command(name){if(!["save","undo","changes","discard"].includes(name))throw Error("Unsupported editor control");await $("ed-"+name).onclick();}
export function dispose(){flushRecovery();cancelAnimationFrame(highlightFrame);highlightFrame=0;window.removeEventListener("beforeunload",beforeUnload);window.removeEventListener('pagehide',flushRecovery);document.removeEventListener('visibilitychange',visibilityRecovery);dirty=false;stack=[];undoBytes=0;lastSource='';opened=null;panel=null;request=null;showFrame=null;}
