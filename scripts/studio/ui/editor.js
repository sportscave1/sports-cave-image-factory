let panel, request, showFrame, opened, dirty=false, busy=false, stack=[], selected="title";
const $=id=>panel.querySelector("#"+id);
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
  const source=$("ed-source").value;
  $("ed-lines").textContent=source.split("\n").map((_,i)=>i+1).join("\n");
  $("ed-highlight").innerHTML=esc(source).replace(/(&lt;\/?[\w-]+|\b(?:const|let|function|return|if|else|var|class|import|export|async|await)\b|#[\da-fA-F]{3,8}\b)/g,'<span class="syntax">$1</span>')+"\n";
}
function capture() {
  if(opened.path!=="app.py") return {source:$("ed-source").value};
  const changes={properties:{}};
  if($("ed-text")) changes.text=$("ed-text").value;
  panel.querySelectorAll("[data-property]").forEach(input=>{changes.properties[input.dataset.property]=input.value;});
  return changes;
}
function apply(value) {
  if(opened.path!=="app.py") { $("ed-source").value=value.source;highlight(); }
  else {
    if($("ed-text")) $("ed-text").value=value.text;
    panel.querySelectorAll("[data-property]").forEach(input=>{input.value=value.properties[input.dataset.property]||"";});
  }
}
function modified() { dirty=true;stack.push(capture());if(stack.length>100)stack.splice(1,1);msg("Unsaved changes"); }
function component() {
  const model=opened.visual[selected], area=$("ed-fields");
  area.replaceChildren();
  const field=(label,value,key)=>{
    const wrap=document.createElement("label"), input=document.createElement("input");
    wrap.textContent=label;input.value=value;
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
  } else { $("ed-source").value=opened.source;highlight();dirty=false;stack=[capture()]; }
  msg("Revision "+opened.revision+" · "+opened.path);
}
async function load(path) {
  opened=await request("/api/action",{action:"editor-open",path});render();
}
async function act(fn) {
  if(busy)return;busy=true;
  panel.querySelectorAll("button").forEach(b=>b.disabled=true);
  try{await fn();}catch(error){msg(error.message);}
  finally{busy=false;panel.querySelectorAll("button").forEach(b=>b.disabled=false);$("ed-restore").disabled=!opened?.history.length;}
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
  await load(opened.path);
  $("ed-diff").textContent=result.diff||"No source changes.";
  if(result.frame)showFrame(result.frame);
  msg(result.preview_error||"Saved to the actual draft. Revision "+opened.revision+".");
}
export async function mount(target,transport,frameCallback) {
  panel=target;request=transport;showFrame=frameCallback;
  if(!panel.dataset.mounted) {
    const css=document.createElement("link");css.rel="stylesheet";css.href="/editor.css";document.head.append(css);
    panel.innerHTML='<div class="heading"><div><p class="eyebrow">DRAFT EDITOR</p><h2>Make a focused change</h2></div><button id="ed-close">Close editor</button></div><p class="hint">Explicit component mappings only. The selected worktree is the source of truth. Live integrations remain disabled.</p><label>Editing target<select id="ed-file"><option value="app.py">Visual · Sign-in and shared submit buttons</option><option>components/sports_cave_top_bar/index.html</option><option>mockups_page.css</option><option>orders_page.css</option><option>components/session_recovery.js</option></select></label><p id="ed-status" role="status"></p><div id="ed-visual"><label>Component<select id="ed-component"></select></label><p class="hint">Properties accept literal hex colours, CSS sizes, and supported alignment/layout values. Empty removes the override. Mobile panel settings apply below 760 px.</p><div id="ed-fields"></div></div><div id="ed-code" hidden><label>Search<input id="ed-search" placeholder="Find source text"></label><button id="ed-find">Find next</button><div class="code-wrap"><pre id="ed-lines" aria-hidden="true"></pre><div class="code-stack"><pre id="ed-highlight" aria-hidden="true"></pre><textarea id="ed-source" wrap="off" spellcheck="false" aria-label="Authorised source code"></textarea></div></div></div><div class="actions"><button class="primary" id="ed-save">Save Draft</button><button id="ed-undo">Undo</button><button id="ed-discard">Discard Unsaved Changes</button><button id="ed-changes">View Changes</button></div><label>Saved editor revision<select id="ed-history"></select></label><button id="ed-restore">Restore Revision</button><pre id="ed-diff" aria-label="Source changes"></pre>';
    $("ed-file").onchange=()=>act(async()=>{
      const path=$("ed-file").value;
      if(dirty&&!await confirmDiscard("Discard unsaved editor changes?")){$("ed-file").value=opened.path;return;}
      await load(path);
    });
    $("ed-component").onchange=async()=>{
      if(dirty&&!await confirmDiscard("Discard unsaved component changes?")){$("ed-component").value=selected;return;}
      selected=$("ed-component").value;component();msg("Editing "+opened.visual[selected].label);
    };
    $("ed-source").oninput=()=>{highlight();modified();};
    $("ed-source").onscroll=()=>{
      $("ed-highlight").scrollTop=$("ed-source").scrollTop;
      $("ed-highlight").scrollLeft=$("ed-source").scrollLeft;
      $("ed-lines").scrollTop=$("ed-source").scrollTop;
    };
    $("ed-find").onclick=()=>{
      const field=$("ed-source"),term=$("ed-search").value;
      let index=field.value.indexOf(term,field.selectionEnd);
      if(index<0)index=field.value.indexOf(term);
      if(index>=0&&term){field.focus();field.setSelectionRange(index,index+term.length);field.scrollTop=field.value.slice(0,index).split("\n").length*20-80;}
      else msg("No match.");
    };
    $("ed-save").onclick=()=>act(()=>save());
    $("ed-undo").onclick=()=>act(async()=>{
      if(dirty&&stack.length>1){stack.pop();apply(stack.at(-1));dirty=stack.length>1;msg(dirty?"Unsaved changes":"Local edits undone.");return;}
      const undone=new Set(opened.history.filter(h=>h.undo_of).map(h=>h.undo_of));
      const latest=[...opened.history].reverse().find(h=>h.operation!=="undo"&&!undone.has(h.id));
      if(latest)await save({id:latest.id,side:"before"});else msg("Nothing to undo.");
    });
    $("ed-discard").onclick=()=>act(async()=>{
      if(dirty&&!await confirmDiscard("Discard unsaved editor changes?"))return;
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
    $("ed-close").onclick=async()=>{if(!dirty||await confirmDiscard("Discard unsaved changes and close?")){dirty=false;panel.hidden=true;}};
    window.addEventListener("beforeunload",event=>{if(dirty){event.preventDefault();event.returnValue="";}});
    panel.dataset.mounted="true";
  }
  panel.hidden=false;
  if(dirty)return;
  await act(()=>load(opened?.path||"app.py"));
}
